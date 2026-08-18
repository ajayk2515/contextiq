from datetime import datetime
from enum import StrEnum
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
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class EvaluationRunStatus(StrEnum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class EvaluationFailureCategory(StrEnum):
    RETRIEVAL = "RETRIEVAL"
    GENERATION = "GENERATION"
    METRIC = "METRIC"
    AUTHORIZATION = "AUTHORIZATION"
    SYSTEM = "SYSTEM"


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('RUNNING', 'COMPLETED', 'FAILED')", name="ck_evaluation_runs_status"
        ),
        CheckConstraint("total_cases >= 0", name="ck_evaluation_runs_total_cases"),
        CheckConstraint("completed_cases >= 0", name="ck_evaluation_runs_completed_cases"),
        CheckConstraint("completed_cases <= total_cases", name="ck_evaluation_runs_progress"),
        Index("ix_evaluation_runs_created_at", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    total_cases: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    completed_cases: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Evaluation(Base):
    __tablename__ = "evaluations"
    __table_args__ = (
        UniqueConstraint("run_id", "evaluation_case_id", name="uq_evaluations_run_case"),
        CheckConstraint(
            "role IN ('Developer', 'HR', 'Finance', 'Executive')", name="ck_evaluations_role"
        ),
        CheckConstraint(
            "failure_category IS NULL OR failure_category IN "
            "('RETRIEVAL', 'GENERATION', 'METRIC', 'AUTHORIZATION', 'SYSTEM')",
            name="ck_evaluations_failure_category",
        ),
        Index("ix_evaluations_run_id", "run_id"),
        Index("ix_evaluations_query_id", "query_id"),
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("evaluation_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    evaluation_case_id: Mapped[str] = mapped_column(String(100), nullable=False)
    query_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("query_logs.id", ondelete="SET NULL"),
        nullable=True,
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    expected_answer: Mapped[str] = mapped_column(Text, nullable=False)
    expected_document: Mapped[str] = mapped_column(String(255), nullable=False)
    generated_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    faithfulness: Mapped[float | None] = mapped_column(Float, nullable=True)
    answer_relevancy: Mapped[float | None] = mapped_column(Float, nullable=True)
    context_precision: Mapped[float | None] = mapped_column(Float, nullable=True)
    context_recall: Mapped[float | None] = mapped_column(Float, nullable=True)
    failure_category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    insufficient_context: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
