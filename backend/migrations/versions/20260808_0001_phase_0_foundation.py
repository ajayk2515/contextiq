"""Create the Phase 0 database foundation.

Revision ID: 20260808_0001
Revises:
Create Date: 2026-08-08
"""

from collections.abc import Sequence

revision: str = "20260808_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply the intentionally empty foundation migration."""


def downgrade() -> None:
    """Revert the intentionally empty foundation migration."""
