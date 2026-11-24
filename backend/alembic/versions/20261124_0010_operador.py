"""Operadores de Microsoft asignados a una faena."""

import sqlalchemy as sa
from alembic import op

revision = "20261124_0010"
down_revision = "20261124_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "operador",
        sa.Column("id_operador", sa.String(), primary_key=True),
        sa.Column("id_faena", sa.String(), sa.ForeignKey("faena.id_faena", ondelete="SET NULL"), nullable=True),
        sa.Column("microsoft_subject", sa.String(255), nullable=False, unique=True),
        sa.Column("nombre", sa.String(120), nullable=False),
        sa.Column("correo", sa.String(255), nullable=False),
    )
    op.create_index("ix_operador_id_faena", "operador", ["id_faena"])


def downgrade() -> None:
    op.drop_index("ix_operador_id_faena", table_name="operador")
    op.drop_table("operador")
