from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class QueryLog(Base):
    __tablename__ = "query_logs"
    __table_args__ = (
        CheckConstraint(
            "query_category IN ('FAQ', 'SPECIFIC_SEARCH', 'MULTI_DOC_COMPARISON', "
            "'SUMMARIZATION', 'RESTRICTED_DATA')",
            name="ck_query_logs_category",
        ),
        CheckConstraint(
            "retrieval_profile IN ('FAST', 'BALANCED', 'ACCURATE')",
            name="ck_query_logs_profile",
        ),
        CheckConstraint(
            "retrieval_strategy IN ('DENSE', 'DENSE_FALLBACK', 'HYBRID_RRF', 'HYBRID_RRF_RERANK')",
            name="ck_query_logs_strategy",
        ),
        CheckConstraint("retrieval_latency_ms >= 0", name="ck_query_logs_retrieval_latency"),
        Index("ix_query_logs_user_id", "user_id"),
        Index("ix_query_logs_created_at", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    query_category: Mapped[str] = mapped_column(String(32), nullable=False)
    retrieval_profile: Mapped[str] = mapped_column(String(16), nullable=False)
    retrieval_strategy: Mapped[str] = mapped_column(String(32), nullable=False)
    classifier_fallback: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    retrieval_latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class RetrievalLog(Base):
    __tablename__ = "retrieval_logs"
    __table_args__ = (
        CheckConstraint(
            "rank_before IS NULL OR rank_before > 0", name="ck_retrieval_logs_rank_before"
        ),
        CheckConstraint(
            "rank_after IS NULL OR rank_after > 0", name="ck_retrieval_logs_rank_after"
        ),
        Index("ix_retrieval_logs_query_id", "query_id"),
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    query_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("query_logs.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    chunk_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section: Mapped[str | None] = mapped_column(Text, nullable=True)
    snippet: Mapped[str] = mapped_column(Text, nullable=False)
    rank_before: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rank_after: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retrieval_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    rrf_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    reranker_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    included_in_context: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
