# File purpose: Defines the 20260804 0010 file ownership database schema migration and rollback.
# Main declarations: upgrade handles upgrade; downgrade handles downgrade.

"""add file ownership

Revision ID: 20260804_0010
Revises: 20260803_0009
Create Date: 2026-08-04 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260804_0010"
down_revision: str | None = "20260803_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("files", sa.Column("user_id", sa.String(length=32), nullable=True))
    op.create_foreign_key("fk_files_user_id_users", "files", "users", ["user_id"], ["id"])
    op.create_index(op.f("ix_files_user_id"), "files", ["user_id"], unique=False)
    op.execute(
        """
        UPDATE files
        SET user_id = conversations.user_id
        FROM conversations
        WHERE files.conversation_id = conversations.id
          AND files.user_id IS NULL
        """
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_files_user_id"), table_name="files")
    op.drop_constraint("fk_files_user_id_users", "files", type_="foreignkey")
    op.drop_column("files", "user_id")
