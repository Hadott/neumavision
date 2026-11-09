"""Add criticidad_manual column to imagen (clasificacion manual del revisor)."""

from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20261027_0007"
down_revision: str | None = "20261005_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("imagen", sa.Column("criticidad_manual", sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column("imagen", "criticidad_manual")
