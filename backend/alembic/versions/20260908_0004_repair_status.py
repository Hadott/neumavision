"""Add estado_reparacion column to deteccion."""

from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260908_0004"
down_revision: str | None = "20260902_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "deteccion",
        sa.Column("estado_reparacion", sa.String(length=30), nullable=False, server_default="pending"),
    )
    op.create_index(
        op.f("ix_deteccion_estado_reparacion"), "deteccion", ["estado_reparacion"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_deteccion_estado_reparacion"), table_name="deteccion")
    op.drop_column("deteccion", "estado_reparacion")
