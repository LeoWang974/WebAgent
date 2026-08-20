# File purpose: Aligns Artifact query indexes after durable Run ownership was introduced.
# Main declarations: upgrade replaces a redundant Run index and adds the artifact list index;
# downgrade restores the previous index layout.

"""optimize artifact state and run ownership queries

Revision ID: 20260819_0013
Revises: 20260819_0012
Create Date: 2026-08-19 12:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260819_0013"
down_revision: str | None = "20260819_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("ix_run_artifacts_run_id", table_name="run_artifacts")
    op.create_index(
        "ix_artifacts_conversation_status_created",
        "artifacts",
        ["conversation_id", "status", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_artifacts_conversation_status_created", table_name="artifacts")
    op.create_index(
        "ix_run_artifacts_run_id",
        "run_artifacts",
        ["run_id"],
        unique=False,
    )
