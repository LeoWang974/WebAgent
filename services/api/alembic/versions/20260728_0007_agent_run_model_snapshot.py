# File purpose: Defines the 20260728 0007 agent run model snapshot database schema migration and
# rollback.
# Main declarations: upgrade handles upgrade; downgrade handles downgrade.

"""add agent run model snapshot

Revision ID: 20260728_0007
Revises: 20260721_0006
Create Date: 2026-07-28
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260728_0007"
down_revision: str | None = "20260721_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_runs",
        sa.Column("model_config_id", sa.String(), nullable=True),
    )
    op.add_column(
        "agent_runs",
        sa.Column("model_provider", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "agent_runs",
        sa.Column("model_name", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "agent_runs",
        sa.Column("model_base_url", sa.String(length=1024), nullable=True),
    )
    op.add_column(
        "agent_runs",
        sa.Column("model_api_key_snapshot", sa.Text(), nullable=True),
    )
    op.create_foreign_key(
        "fk_agent_runs_model_config_id_model_configs",
        "agent_runs",
        "model_configs",
        ["model_config_id"],
        ["id"],
    )
    op.create_index(
        op.f("ix_agent_runs_model_config_id"),
        "agent_runs",
        ["model_config_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_agent_runs_model_config_id"), table_name="agent_runs")
    op.drop_constraint(
        "fk_agent_runs_model_config_id_model_configs",
        "agent_runs",
        type_="foreignkey",
    )
    op.drop_column("agent_runs", "model_api_key_snapshot")
    op.drop_column("agent_runs", "model_base_url")
    op.drop_column("agent_runs", "model_name")
    op.drop_column("agent_runs", "model_provider")
    op.drop_column("agent_runs", "model_config_id")
