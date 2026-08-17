"""Create query logs table.

Revision ID: 20260817_0004
Revises: 20260811_0003
Create Date: 2026-08-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260817_0004"
down_revision: str | None = "20260811_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "query_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("query_category", sa.String(length=32), nullable=False),
        sa.Column("retrieval_profile", sa.String(length=16), nullable=False),
        sa.Column("retrieval_strategy", sa.String(length=32), nullable=False),
        sa.Column("classifier_fallback", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("retrieval_latency_ms", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "query_category IN ('FAQ', 'SPECIFIC_SEARCH', 'MULTI_DOC_COMPARISON', "
            "'SUMMARIZATION', 'RESTRICTED_DATA')",
            name="ck_query_logs_category",
        ),
        sa.CheckConstraint(
            "retrieval_profile IN ('FAST', 'BALANCED', 'ACCURATE')",
            name="ck_query_logs_profile",
        ),
        sa.CheckConstraint(
            "retrieval_strategy IN ('DENSE', 'DENSE_FALLBACK')",
            name="ck_query_logs_strategy",
        ),
        sa.CheckConstraint("retrieval_latency_ms >= 0", name="ck_query_logs_retrieval_latency"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_query_logs_created_at", "query_logs", ["created_at"])
    op.create_index("ix_query_logs_user_id", "query_logs", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_query_logs_user_id", table_name="query_logs")
    op.drop_index("ix_query_logs_created_at", table_name="query_logs")
    op.drop_table("query_logs")
