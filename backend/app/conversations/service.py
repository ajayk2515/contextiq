from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.errors import raise_conversation_not_found
from app.conversations.models import Conversation, Message, MessageRole
from app.conversations.schemas import ConversationDetail, ConversationMessage
from app.database import AsyncSessionFactory
from app.query_intelligence.domain import QueryCategory, RetrievalProfile
from app.query_intelligence.models import QueryLog
from app.query_intelligence.profiles import profile_config
from app.rag.prompting import ConversationHistoryMessage
from app.rag.schemas import ChatSource, QueryIntelligenceMetadata

DEFAULT_CONVERSATION_TITLE = "New conversation"
TITLE_MAX_LENGTH = 72


@dataclass(frozen=True)
class ConversationTurn:
    conversation_id: UUID
    user_message_id: UUID
    history: list[ConversationHistoryMessage]


def conversation_title(message: str) -> str:
    normalized = " ".join(message.split())
    if len(normalized) <= TITLE_MAX_LENGTH:
        return normalized
    return normalized[: TITLE_MAX_LENGTH - 3].rstrip() + "..."


def owned_conversation_query(conversation_id: UUID, user_id: UUID) -> Select[tuple[Conversation]]:
    return select(Conversation).where(
        Conversation.id == conversation_id,
        Conversation.user_id == user_id,
    )


async def get_owned_conversation(
    session: AsyncSession, conversation_id: UUID, user_id: UUID
) -> Conversation:
    result = await session.execute(owned_conversation_query(conversation_id, user_id))
    conversation = result.scalar_one_or_none()
    if conversation is None:
        raise_conversation_not_found()
    return conversation


def message_response(message: Message, query_log: QueryLog | None = None) -> ConversationMessage:
    query_intelligence = None
    if query_log is not None:
        profile = profile_config(RetrievalProfile(query_log.retrieval_profile))
        query_intelligence = QueryIntelligenceMetadata(
            query_id=query_log.id,
            category=QueryCategory(query_log.query_category),
            profile=profile.profile,
            intended_strategy=profile.intended_strategy,
            executed_strategy=profile.executed_strategy,
            candidate_top_k=profile.candidate_top_k,
            classification_fallback=query_log.classifier_fallback,
        )
    return ConversationMessage(
        id=message.id,
        role=MessageRole(message.role),
        content=message.content,
        query_id=message.query_id,
        query_intelligence=query_intelligence,
        sources=[ChatSource.model_validate(source) for source in message.sources],
        insufficient_context=message.insufficient_context,
        created_at=message.created_at,
    )


async def conversation_detail(
    session: AsyncSession, conversation_id: UUID, user_id: UUID
) -> ConversationDetail:
    conversation = await get_owned_conversation(session, conversation_id, user_id)
    result = await session.execute(
        select(Message, QueryLog)
        .outerjoin(QueryLog, QueryLog.id == Message.query_id)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.created_at, Message.id)
    )
    return ConversationDetail(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        messages=[message_response(message, query_log) for message, query_log in result.all()],
    )


class ConversationStore:
    async def begin_turn(
        self,
        conversation_id: UUID,
        user_id: UUID,
        content: str,
        history_limit: int,
    ) -> ConversationTurn:
        async with AsyncSessionFactory() as session:
            conversation = await get_owned_conversation(session, conversation_id, user_id)
            result = await session.execute(
                select(Message)
                .where(Message.conversation_id == conversation.id)
                .order_by(Message.created_at.desc(), Message.id.desc())
                .limit(history_limit)
            )
            recent = list(reversed(result.scalars().all()))
            history = [
                ConversationHistoryMessage(
                    role="user" if message.role == MessageRole.USER else "assistant",
                    content=message.content,
                )
                for message in recent
            ]

            user_message = Message(
                conversation_id=conversation.id,
                role=MessageRole.USER,
                content=content,
                sources=[],
            )
            session.add(user_message)
            if conversation.title == DEFAULT_CONVERSATION_TITLE and not recent:
                conversation.title = conversation_title(content)
            conversation.updated_at = datetime.now(UTC)
            await session.commit()
            await session.refresh(user_message)
            return ConversationTurn(conversation.id, user_message.id, history)

    async def persist_assistant(
        self,
        conversation_id: UUID,
        user_id: UUID,
        content: str,
        query_id: UUID,
        sources: list[ChatSource],
        insufficient_context: bool,
    ) -> Message:
        async with AsyncSessionFactory() as session:
            conversation = await get_owned_conversation(session, conversation_id, user_id)
            assistant_message = Message(
                conversation_id=conversation.id,
                role=MessageRole.ASSISTANT,
                content=content,
                query_id=query_id,
                sources=[source.model_dump(mode="json") for source in sources],
                insufficient_context=insufficient_context,
            )
            session.add(assistant_message)
            conversation.updated_at = datetime.now(UTC)
            await session.commit()
            await session.refresh(assistant_message)
            return assistant_message
