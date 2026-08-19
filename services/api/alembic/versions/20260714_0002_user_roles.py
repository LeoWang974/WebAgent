# File purpose: Defines the 20260714 0002 user roles database schema migration and rollback.
# Main declarations: upgrade handles upgrade; downgrade handles downgrade.

"""add user roles

Revision ID: 20260714_0002
Revises: 20260710_0001
Create Date: 2026-07-14
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260714_0002"
down_revision: str | None = "20260710_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("role", sa.String(length=50), server_default="user", nullable=False),
    )
    op.alter_column("users", "role", server_default=None)


def downgrade() -> None:
    op.drop_column("users", "role")
