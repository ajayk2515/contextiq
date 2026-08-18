"""Create persisted RAGAS evaluation runs and results.

Revision ID: 20260818_0009
Revises: 20260818_0008
Create Date: 2026-08-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260818_0009"
down_revision: str | None = "20260818_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "evaluation_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("total_cases", sa.Integer(), server_default="0", nullable=False),
        sa.Column("completed_cases", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('RUNNING', 'COMPLETED', 'FAILED')",
            name="ck_evaluation_runs_status",
        ),
        sa.CheckConstraint("total_cases >= 0", name="ck_evaluation_runs_total_cases"),
        sa.CheckConstraint("completed_cases >= 0", name="ck_evaluation_runs_completed_cases"),
        sa.CheckConstraint("completed_cases <= total_cases", name="ck_evaluation_runs_progress"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_evaluation_runs_created_at", "evaluation_runs", ["created_at"])
    op.create_table(
        "evaluations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evaluation_case_id", sa.String(length=100), nullable=False),
        sa.Column("query_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("expected_answer", sa.Text(), nullable=False),
        sa.Column("expected_document", sa.String(length=255), nullable=False),
        sa.Column("generated_answer", sa.Text(), nullable=True),
        sa.Column("faithfulness", sa.Float(), nullable=True),
        sa.Column("answer_relevancy", sa.Float(), nullable=True),
        sa.Column("context_precision", sa.Float(), nullable=True),
        sa.Column("context_recall", sa.Float(), nullable=True),
        sa.Column("failure_category", sa.String(length=32), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("insufficient_context", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role IN ('Developer', 'HR', 'Finance', 'Executive')",
            name="ck_evaluations_role",
        ),
        sa.CheckConstraint(
            "failure_category IS NULL OR failure_category IN "
            "('RETRIEVAL', 'GENERATION', 'METRIC', 'AUTHORIZATION', 'SYSTEM')",
            name="ck_evaluations_failure_category",
        ),
        sa.ForeignKeyConstraint(["query_id"], ["query_logs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["run_id"], ["evaluation_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "evaluation_case_id", name="uq_evaluations_run_case"),
    )
    op.create_index("ix_evaluations_query_id", "evaluations", ["query_id"])
    op.create_index("ix_evaluations_run_id", "evaluations", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_evaluations_run_id", table_name="evaluations")
    op.drop_index("ix_evaluations_query_id", table_name="evaluations")
    op.drop_table("evaluations")
    op.drop_index("ix_evaluation_runs_created_at", table_name="evaluation_runs")
    op.drop_table("evaluation_runs")
