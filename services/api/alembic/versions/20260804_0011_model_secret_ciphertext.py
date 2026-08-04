"""allow versioned model credential ciphertext

Revision ID: 20260804_0011
Revises: 20260804_0010
Create Date: 2026-08-04 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260804_0011"
down_revision: str | None = "20260804_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "model_configs",
        "encrypted_api_key",
        existing_type=sa.String(length=2048),
        type_=sa.Text(),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "model_configs",
        "encrypted_api_key",
        existing_type=sa.Text(),
        type_=sa.String(length=2048),
        existing_nullable=True,
    )
