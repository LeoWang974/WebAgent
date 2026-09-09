# File purpose: Adds database indexes for long-conversation and agent-event queries.
# Main declarations: upgrade creates runtime query indexes; downgrade removes them.

"""Add indexes for long-conversation and agent-event queries."""

from collections.abc import Sequence

from alembic import op


revision: str = "20260904_0014"
down_revision: str | None = "20260819_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_agent_run_events_run_created_id",
        "agent_run_events",
        ["run_id", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_files_conversation_created",
        "files",
        ["conversation_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_conversations_user_updated",
        "conversations",
        ["user_id", "updated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_conversations_user_updated", table_name="conversations")
    op.drop_index("ix_files_conversation_created", table_name="files")
    op.drop_index("ix_agent_run_events_run_created_id", table_name="agent_run_events")
