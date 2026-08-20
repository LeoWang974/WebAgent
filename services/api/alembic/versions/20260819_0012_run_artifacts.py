# File purpose: Adds durable Agent Run to Artifact ownership records and backfills legacy rows.
# Main declarations: upgrade creates and backfills run_artifacts; downgrade removes it.

"""add run artifact ownership relationships

Revision ID: 20260819_0012
Revises: 20260804_0011
Create Date: 2026-08-19 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260819_0012"
down_revision: str | None = "20260804_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "run_artifacts",
        sa.Column("run_id", sa.String(length=32), nullable=False),
        sa.Column("artifact_id", sa.String(length=32), nullable=False),
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["artifact_id"], ["artifacts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id",
            "artifact_id",
            name="uq_run_artifacts_run_artifact",
        ),
    )
    op.create_index(
        "ix_run_artifacts_artifact_id",
        "run_artifacts",
        ["artifact_id"],
        unique=False,
    )
    op.create_index(
        "ix_run_artifacts_run_created",
        "run_artifacts",
        ["run_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_run_artifacts_run_id",
        "run_artifacts",
        ["run_id"],
        unique=False,
    )

    # Artifact IDs are already unique 32-character values, so they are safe
    # deterministic relationship IDs for the one legacy owner of each row.
    op.execute(
        sa.text(
            """
            INSERT INTO run_artifacts (id, run_id, artifact_id, created_at, updated_at)
            SELECT id, run_id, id, created_at, updated_at
            FROM artifacts
            WHERE run_id IS NOT NULL
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_run_artifacts_run_id", table_name="run_artifacts")
    op.drop_index("ix_run_artifacts_run_created", table_name="run_artifacts")
    op.drop_index("ix_run_artifacts_artifact_id", table_name="run_artifacts")
    op.drop_table("run_artifacts")
