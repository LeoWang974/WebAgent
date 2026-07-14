"""add agent and artifact query indexes

Revision ID: 20260714_0004
Revises: 20260714_0003
Create Date: 2026-07-14
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260714_0004"
down_revision: str | None = "20260714_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_agent_runs_conversation_status_updated",
        "agent_runs",
        ["conversation_id", "status", "updated_at"],
        unique=False,
    )
    op.create_index(
        "ix_artifacts_conversation_run_type",
        "artifacts",
        ["conversation_id", "run_id", "type"],
        unique=False,
    )
    op.create_index(
        "ix_messages_conversation_created",
        "messages",
        ["conversation_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_messages_conversation_created", table_name="messages")
    op.drop_index("ix_artifacts_conversation_run_type", table_name="artifacts")
    op.drop_index("ix_agent_runs_conversation_status_updated", table_name="agent_runs")
