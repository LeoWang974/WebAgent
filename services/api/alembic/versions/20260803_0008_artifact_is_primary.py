# File purpose: Defines the 20260803 0008 artifact is primary database schema migration and
# rollback.
# Main declarations: upgrade handles upgrade; downgrade handles downgrade.

"""add artifact is_primary

Revision ID: 20260803_0008
Revises: 20260728_0007
Create Date: 2026-08-03 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260803_0008"
down_revision: str | None = "20260728_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "artifacts",
        sa.Column("is_primary", sa.Boolean(), server_default=sa.true(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("artifacts", "is_primary")
