"""Allow hybrid RRF query-log strategy.

Revision ID: 20260818_0005
Revises: 20260817_0004
Create Date: 2026-08-18
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260818_0005"
down_revision: str | None = "20260817_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_query_logs_strategy", "query_logs", type_="check")
    op.create_check_constraint(
        "ck_query_logs_strategy",
        "query_logs",
        "retrieval_strategy IN ('DENSE', 'DENSE_FALLBACK', 'HYBRID_RRF')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_query_logs_strategy", "query_logs", type_="check")
    op.create_check_constraint(
        "ck_query_logs_strategy",
        "query_logs",
        "retrieval_strategy IN ('DENSE', 'DENSE_FALLBACK')",
    )
