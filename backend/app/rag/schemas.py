from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.query_intelligence.domain import (
    ExecutedRetrievalStrategy,
    IntendedRetrievalStrategy,
    QueryCategory,
    RetrievalProfile,
)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=2000)

    @field_validator("message")
    @classmethod
    def require_non_whitespace_message(cls, value: str) -> str:
        message = value.strip()
        if not message:
            raise ValueError("Message must not be empty.")
        return message


class ChatSource(BaseModel):
    document_id: UUID
    chunk_id: UUID
    filename: str
    page: int | None
    section: str | None
    snippet: str


class QueryIntelligenceMetadata(BaseModel):
    query_id: UUID
    category: QueryCategory
    profile: RetrievalProfile
    intended_strategy: IntendedRetrievalStrategy
    executed_strategy: ExecutedRetrievalStrategy
    candidate_top_k: int
    classification_fallback: bool


class ChatResponse(BaseModel):
    answer: str
    sources: list[ChatSource]
    insufficient_context: bool
    query_intelligence: QueryIntelligenceMetadata
