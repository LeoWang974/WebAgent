# File purpose: Defines the 20260721 0006 conversation folders database schema migration and
# rollback.
# Main declarations: upgrade handles upgrade; downgrade handles downgrade.

"""add conversation folders

Revision ID: 20260721_0006
Revises: 20260717_0005
Create Date: 2026-07-21
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260721_0006"
down_revision: str | None = "20260717_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "conversation_folders",
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "name", name="uq_conversation_folder_user_name"),
    )
    op.create_index(
        op.f("ix_conversation_folders_user_id"),
        "conversation_folders",
        ["user_id"],
        unique=False,
    )
    op.add_column("conversations", sa.Column("folder_id", sa.String(), nullable=True))
    op.create_index(
        op.f("ix_conversations_folder_id"),
        "conversations",
        ["folder_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_conversations_folder_id_conversation_folders",
        "conversations",
        "conversation_folders",
        ["folder_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_conversations_folder_id_conversation_folders",
        "conversations",
        type_="foreignkey",
    )
    op.drop_index(op.f("ix_conversations_folder_id"), table_name="conversations")
    op.drop_column("conversations", "folder_id")
    op.drop_index(op.f("ix_conversation_folders_user_id"), table_name="conversation_folders")
    op.drop_table("conversation_folders")
