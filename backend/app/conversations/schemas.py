from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.conversations.models import MessageRole
from app.rag.schemas import ChatSource, QueryIntelligenceMetadata


class ConversationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime


class ConversationMessage(BaseModel):
    id: UUID
    role: MessageRole
    content: str
    query_id: UUID | None
    query_intelligence: QueryIntelligenceMetadata | None = None
    sources: list[ChatSource]
    insufficient_context: bool
    created_at: datetime


class ConversationDetail(ConversationSummary):
    messages: list[ConversationMessage]
