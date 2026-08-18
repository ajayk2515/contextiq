from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser
from app.conversations.models import Conversation
from app.conversations.schemas import ConversationDetail, ConversationSummary
from app.conversations.service import (
    DEFAULT_CONVERSATION_TITLE,
    conversation_detail,
    get_owned_conversation,
)
from app.database import get_session

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.post("", response_model=ConversationSummary, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Conversation:
    conversation = Conversation(user_id=current_user.id, title=DEFAULT_CONVERSATION_TITLE)
    session.add(conversation)
    await session.commit()
    await session.refresh(conversation)
    return conversation


@router.get("", response_model=list[ConversationSummary])
async def list_conversations(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[Conversation]:
    result = await session.execute(
        select(Conversation)
        .where(Conversation.user_id == current_user.id)
        .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
    )
    return list(result.scalars().all())


@router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: UUID,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ConversationDetail:
    return await conversation_detail(session, conversation_id, current_user.id)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: UUID,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    conversation = await get_owned_conversation(session, conversation_id, current_user.id)
    await session.delete(conversation)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
