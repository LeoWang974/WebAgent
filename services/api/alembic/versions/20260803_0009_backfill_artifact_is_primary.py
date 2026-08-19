# File purpose: Defines the 20260803 0009 backfill artifact is primary database schema migration and
# rollback.
# Main declarations: upgrade handles upgrade; downgrade handles downgrade.

"""backfill artifact is_primary

Revision ID: 20260803_0009
Revises: 20260803_0008
Create Date: 2026-08-03 00:10:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260803_0009"
down_revision: str | None = "20260803_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE artifacts
        SET is_primary = false
        WHERE type = 'debug_json'
           OR artifact_metadata ->> 'developerOnly' = 'true'
           OR artifact_metadata ->> 'artifactRole' IN ('intermediate', 'preview_fallback')
           OR (
                type = 'html_page'
                AND lower(coalesce(artifact_metadata ->> 'path', '')) LIKE '%/pages/page_%'
           )
        """
    )


def downgrade() -> None:
    op.execute("UPDATE artifacts SET is_primary = true")
