# File purpose: Defines the 20260710 0001 core persistence database schema migration and rollback.
# Main declarations: create_timestamp_columns creates timestamp columns; upgrade handles upgrade;
# downgrade handles downgrade.

"""core persistence baseline

Revision ID: 20260710_0001
Revises:
Create Date: 2026-07-10
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260710_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def create_timestamp_columns() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=True),
        sa.Column("nickname", sa.String(length=120), nullable=False),
        sa.Column("avatar_url", sa.String(length=1024), nullable=True),
        sa.Column("id", sa.String(length=32), nullable=False),
        *create_timestamp_columns(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    op.create_table(
        "skill_configs",
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("current_version", sa.String(length=40), nullable=False),
        sa.Column("id", sa.String(length=32), nullable=False),
        *create_timestamp_columns(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_skill_configs_key"), "skill_configs", ["key"], unique=True)

    op.create_table(
        "skill_versions",
        sa.Column("skill_key", sa.String(length=80), nullable=False),
        sa.Column("version", sa.String(length=40), nullable=False),
        sa.Column("changelog", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("id", sa.String(length=32), nullable=False),
        *create_timestamp_columns(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_skill_versions_skill_key"), "skill_versions", ["skill_key"], unique=False
    )

    op.create_table(
        "conversations",
        sa.Column("user_id", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("type", sa.String(length=50), nullable=False),
        sa.Column("pinned", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("visibility", sa.String(length=20), nullable=False),
        sa.Column("id", sa.String(length=32), nullable=False),
        *create_timestamp_columns(),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_conversations_user_id"), "conversations", ["user_id"], unique=False)

    op.create_table(
        "model_configs",
        sa.Column("user_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("base_url", sa.String(length=1024), nullable=True),
        sa.Column("encrypted_api_key", sa.String(length=2048), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("is_available", sa.Boolean(), nullable=False),
        sa.Column("id", sa.String(length=32), nullable=False),
        *create_timestamp_columns(),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_model_configs_user_id"), "model_configs", ["user_id"], unique=False)

    op.create_table(
        "user_settings",
        sa.Column("user_id", sa.String(length=32), nullable=False),
        sa.Column("data_context", sa.JSON(), nullable=False),
        sa.Column("interface", sa.JSON(), nullable=False),
        sa.Column("id", sa.String(length=32), nullable=False),
        *create_timestamp_columns(),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_user_settings_user_id"), "user_settings", ["user_id"], unique=True)

    op.create_table(
        "conversation_shares",
        sa.Column("conversation_id", sa.String(length=32), nullable=False),
        sa.Column("user_id", sa.String(length=32), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column("id", sa.String(length=32), nullable=False),
        *create_timestamp_columns(),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("conversation_id", "user_id", name="uq_conversation_share_user"),
    )
    op.create_index(
        op.f("ix_conversation_shares_conversation_id"),
        "conversation_shares",
        ["conversation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_conversation_shares_user_id"), "conversation_shares", ["user_id"], unique=False
    )

    op.create_table(
        "messages",
        sa.Column("conversation_id", sa.String(length=32), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("artifact_ids", sa.JSON(), nullable=True),
        sa.Column("id", sa.String(length=32), nullable=False),
        *create_timestamp_columns(),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_messages_conversation_id"), "messages", ["conversation_id"], unique=False
    )

    op.create_table(
        "agent_runs",
        sa.Column("conversation_id", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("id", sa.String(length=32), nullable=False),
        *create_timestamp_columns(),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_agent_runs_conversation_id"), "agent_runs", ["conversation_id"], unique=False
    )

    op.create_table(
        "files",
        sa.Column("conversation_id", sa.String(length=32), nullable=True),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("storage_key", sa.String(length=1024), nullable=False),
        sa.Column("file_metadata", sa.JSON(), nullable=True),
        sa.Column("id", sa.String(length=32), nullable=False),
        *create_timestamp_columns(),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "agent_run_events",
        sa.Column("run_id", sa.String(length=32), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("id", sa.String(length=32), nullable=False),
        *create_timestamp_columns(),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_agent_run_events_run_id"), "agent_run_events", ["run_id"], unique=False
    )

    op.create_table(
        "artifacts",
        sa.Column("conversation_id", sa.String(length=32), nullable=False),
        sa.Column("run_id", sa.String(length=32), nullable=True),
        sa.Column("type", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("artifact_metadata", sa.JSON(), nullable=True),
        sa.Column("id", sa.String(length=32), nullable=False),
        *create_timestamp_columns(),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_artifacts_conversation_id"), "artifacts", ["conversation_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_artifacts_conversation_id"), table_name="artifacts")
    op.drop_table("artifacts")
    op.drop_index(op.f("ix_agent_run_events_run_id"), table_name="agent_run_events")
    op.drop_table("agent_run_events")
    op.drop_table("files")
    op.drop_index(op.f("ix_agent_runs_conversation_id"), table_name="agent_runs")
    op.drop_table("agent_runs")
    op.drop_index(op.f("ix_messages_conversation_id"), table_name="messages")
    op.drop_table("messages")
    op.drop_index(op.f("ix_conversation_shares_user_id"), table_name="conversation_shares")
    op.drop_index(op.f("ix_conversation_shares_conversation_id"), table_name="conversation_shares")
    op.drop_table("conversation_shares")
    op.drop_index(op.f("ix_user_settings_user_id"), table_name="user_settings")
    op.drop_table("user_settings")
    op.drop_index(op.f("ix_model_configs_user_id"), table_name="model_configs")
    op.drop_table("model_configs")
    op.drop_index(op.f("ix_conversations_user_id"), table_name="conversations")
    op.drop_table("conversations")
    op.drop_index(op.f("ix_skill_versions_skill_key"), table_name="skill_versions")
    op.drop_table("skill_versions")
    op.drop_index(op.f("ix_skill_configs_key"), table_name="skill_configs")
    op.drop_table("skill_configs")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
