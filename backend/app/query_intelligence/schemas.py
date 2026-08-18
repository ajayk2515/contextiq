from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.query_intelligence.domain import (
    ExecutedRetrievalStrategy,
    QueryCategory,
    RetrievalProfile,
)


class QuerySummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    query_text: str
    query_category: QueryCategory
    retrieval_profile: RetrievalProfile
    retrieval_strategy: ExecutedRetrievalStrategy
    retrieval_latency_ms: int
    classifier_fallback: bool
    created_at: datetime


class QueryDetail(QuerySummary):
    candidate_count: int
    final_context_count: int
    reranked: bool


class RetrievalSnapshot(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    query_id: UUID
    document_id: UUID
    chunk_id: UUID
    filename: str
    page: int | None
    section: str | None
    snippet: str
    rank_before: int | None
    rank_after: int | None
    retrieval_score: float | None
    rrf_score: float | None
    reranker_score: float | None
    included_in_context: bool
    created_at: datetime
