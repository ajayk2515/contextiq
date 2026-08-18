"""Create deterministic optimization recommendations.

Revision ID: 20260818_0010
Revises: 20260818_0009
Create Date: 2026-08-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260818_0010"
down_revision: str | None = "20260818_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "optimization_recommendations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evaluation_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("metric", sa.String(length=32), nullable=False),
        sa.Column("current_value", sa.Float(), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("recommendation", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("profile", sa.String(length=16), nullable=True),
        sa.Column("strategy", sa.String(length=32), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "metric IN ('CONTEXT_RECALL', 'CONTEXT_PRECISION', 'RETRIEVAL_LATENCY_MS')",
            name="ck_optimization_recommendations_metric",
        ),
        sa.CheckConstraint(
            "status IN ('OPEN', 'DISMISSED')",
            name="ck_optimization_recommendations_status",
        ),
        sa.CheckConstraint(
            "profile IS NULL OR profile IN ('FAST', 'BALANCED', 'ACCURATE')",
            name="ck_optimization_recommendations_profile",
        ),
        sa.CheckConstraint(
            "strategy IS NULL OR strategy IN "
            "('DENSE', 'DENSE_FALLBACK', 'HYBRID_RRF', 'HYBRID_RRF_RERANK')",
            name="ck_optimization_recommendations_strategy",
        ),
        sa.CheckConstraint("current_value >= 0", name="ck_optimization_recommendations_value"),
        sa.CheckConstraint("threshold >= 0", name="ck_optimization_recommendations_threshold"),
        sa.ForeignKeyConstraint(["evaluation_run_id"], ["evaluation_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "evaluation_run_id",
            "metric",
            "profile",
            "strategy",
            name="uq_optimization_recommendations_run_rule",
        ),
    )
    op.create_index(
        "ix_optimization_recommendations_run_id",
        "optimization_recommendations",
        ["evaluation_run_id"],
    )
    op.create_index(
        "ix_optimization_recommendations_status",
        "optimization_recommendations",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_optimization_recommendations_status",
        table_name="optimization_recommendations",
    )
    op.drop_index(
        "ix_optimization_recommendations_run_id",
        table_name="optimization_recommendations",
    )
    op.drop_table("optimization_recommendations")
