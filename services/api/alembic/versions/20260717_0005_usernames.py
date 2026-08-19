# File purpose: Defines the 20260717 0005 usernames database schema migration and rollback.
# Main declarations: upgrade handles upgrade; downgrade handles downgrade.

"""add usernames

Revision ID: 20260717_0005
Revises: 20260714_0004
Create Date: 2026-07-17
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260717_0005"
down_revision: str | None = "20260714_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("username", sa.String(length=80), nullable=True))
    op.create_index(op.f("ix_users_username"), "users", ["username"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_users_username"), table_name="users")
    op.drop_column("users", "username")
