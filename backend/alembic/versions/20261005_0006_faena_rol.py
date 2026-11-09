"""Add rol column to faena (admin / faena)."""

from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20261005_0006"
down_revision: str | None = "20261005_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("faena", sa.Column("rol", sa.String(length=20), nullable=False, server_default="faena"))


def downgrade() -> None:
    op.drop_column("faena", "rol")
