"""Add fecha_reparacion column to deteccion."""

from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20261005_0005"
down_revision: str | None = "20260908_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("deteccion", sa.Column("fecha_reparacion", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("deteccion", "fecha_reparacion")
