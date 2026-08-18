from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from types import TracebackType
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.conversations.models import Conversation, Message, MessageRole
from app.conversations.service import ConversationStore, conversation_title
from app.rag.schemas import ChatSource


class SessionContext(AbstractAsyncContextManager[MagicMock]):
    def __init__(self, session: MagicMock) -> None:
        self.session = session

    async def __aenter__(self) -> MagicMock:
        return self.session

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None


def test_conversation_title_is_normalized_and_deterministically_truncated() -> None:
    assert conversation_title("  Compare   leave policies  ") == "Compare leave policies"
    long_title = conversation_title("x" * 100)
    assert len(long_title) == 72
    assert long_title.endswith("...")


async def test_begin_turn_selects_bounded_history_and_persists_user_message() -> None:
    user_id = uuid4()
    conversation = Conversation(id=uuid4(), user_id=user_id, title="New conversation")
    now = datetime.now(UTC)
    recent = [
        Message(
            id=uuid4(),
            conversation_id=conversation.id,
            role=MessageRole.USER,
            content="First question",
            sources=[],
            created_at=now,
        ),
        Message(
            id=uuid4(),
            conversation_id=conversation.id,
            role=MessageRole.ASSISTANT,
            content="First answer",
            sources=[],
            created_at=now,
        ),
    ]
    owned_result = MagicMock()
    owned_result.scalar_one_or_none.return_value = conversation
    history_result = MagicMock()
    history_result.scalars.return_value.all.return_value = list(reversed(recent))
    session = MagicMock()
    session.execute = AsyncMock(side_effect=[owned_result, history_result])
    session.commit = AsyncMock()

    async def refresh(message: Message) -> None:
        message.id = uuid4()

    session.refresh = AsyncMock(side_effect=refresh)
    with patch(
        "app.conversations.service.AsyncSessionFactory", return_value=SessionContext(session)
    ):
        turn = await ConversationStore().begin_turn(
            conversation.id, user_id, "Follow-up question", 2
        )

    assert [item.content for item in turn.history] == ["First question", "First answer"]
    assert [item.role for item in turn.history] == ["user", "assistant"]
    user_message = session.add.call_args.args[0]
    assert user_message.role == MessageRole.USER
    assert user_message.content == "Follow-up question"
    assert conversation.title == "New conversation"
    history_query = session.execute.await_args_list[1].args[0]
    assert "LIMIT" in str(history_query)
    session.commit.assert_awaited_once()


async def test_first_turn_sets_title_and_assistant_persists_query_and_citations() -> None:
    user_id = uuid4()
    conversation = Conversation(id=uuid4(), user_id=user_id, title="New conversation")
    owned_result = MagicMock()
    owned_result.scalar_one_or_none.return_value = conversation
    empty_history = MagicMock()
    empty_history.scalars.return_value.all.return_value = []
    session = MagicMock()
    session.execute = AsyncMock(side_effect=[owned_result, empty_history])
    session.commit = AsyncMock()

    async def refresh(message: Message) -> None:
        message.id = uuid4()

    session.refresh = AsyncMock(side_effect=refresh)
    with patch(
        "app.conversations.service.AsyncSessionFactory", return_value=SessionContext(session)
    ):
        await ConversationStore().begin_turn(
            conversation.id, user_id, "Compare parental and annual leave", 8
        )
    assert conversation.title == "Compare parental and annual leave"

    query_id = uuid4()
    source = ChatSource(
        document_id=uuid4(),
        chunk_id=uuid4(),
        filename="policy.md",
        page=None,
        section="Leave",
        snippet="Policy citation",
    )
    assistant_session = MagicMock()
    assistant_session.execute = AsyncMock(return_value=owned_result)
    assistant_session.commit = AsyncMock()
    assistant_session.refresh = AsyncMock(side_effect=refresh)
    with patch(
        "app.conversations.service.AsyncSessionFactory",
        return_value=SessionContext(assistant_session),
    ):
        message = await ConversationStore().persist_assistant(
            conversation.id,
            user_id,
            "Grounded answer",
            query_id,
            [source],
            False,
        )

    assert message.role == MessageRole.ASSISTANT
    assert message.query_id == query_id
    assert message.sources[0]["filename"] == "policy.md"
    assistant_session.commit.assert_awaited_once()
