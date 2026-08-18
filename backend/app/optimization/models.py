from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class OptimizationMetric(StrEnum):
    CONTEXT_RECALL = "CONTEXT_RECALL"
    CONTEXT_PRECISION = "CONTEXT_PRECISION"
    RETRIEVAL_LATENCY_MS = "RETRIEVAL_LATENCY_MS"


class OptimizationStatus(StrEnum):
    OPEN = "OPEN"
    DISMISSED = "DISMISSED"


class OptimizationRecommendation(Base):
    __tablename__ = "optimization_recommendations"
    __table_args__ = (
        CheckConstraint(
            "metric IN ('CONTEXT_RECALL', 'CONTEXT_PRECISION', 'RETRIEVAL_LATENCY_MS')",
            name="ck_optimization_recommendations_metric",
        ),
        CheckConstraint(
            "status IN ('OPEN', 'DISMISSED')",
            name="ck_optimization_recommendations_status",
        ),
        CheckConstraint(
            "profile IS NULL OR profile IN ('FAST', 'BALANCED', 'ACCURATE')",
            name="ck_optimization_recommendations_profile",
        ),
        CheckConstraint(
            "strategy IS NULL OR strategy IN "
            "('DENSE', 'DENSE_FALLBACK', 'HYBRID_RRF', 'HYBRID_RRF_RERANK')",
            name="ck_optimization_recommendations_strategy",
        ),
        CheckConstraint("current_value >= 0", name="ck_optimization_recommendations_value"),
        CheckConstraint("threshold >= 0", name="ck_optimization_recommendations_threshold"),
        UniqueConstraint(
            "evaluation_run_id",
            "metric",
            "profile",
            "strategy",
            name="uq_optimization_recommendations_run_rule",
        ),
        Index("ix_optimization_recommendations_run_id", "evaluation_run_id"),
        Index("ix_optimization_recommendations_status", "status"),
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    evaluation_run_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("evaluation_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    metric: Mapped[str] = mapped_column(String(32), nullable=False)
    current_value: Mapped[float] = mapped_column(Float, nullable=False)
    threshold: Mapped[float] = mapped_column(Float, nullable=False)
    recommendation: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    profile: Mapped[str | None] = mapped_column(String(16), nullable=True)
    strategy: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
