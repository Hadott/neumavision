"""Permite cuentas individuales con contraseña conservando los operadores existentes."""

import sqlalchemy as sa
from alembic import op

revision = "20261125_0011"
down_revision = "20261124_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("operador", "microsoft_subject", existing_type=sa.String(255), nullable=True)
    op.add_column("operador", sa.Column("hash_contrasena", sa.String(255), nullable=True))
    op.add_column(
        "operador", sa.Column("fecha_creacion", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.alter_column("operador", "fecha_creacion", server_default=None)
    op.create_index(
        "ux_operador_correo_local", "operador", ["correo"], unique=True,
        postgresql_where=sa.text("hash_contrasena IS NOT NULL"),
    )


def downgrade() -> None:
    op.alter_column("operador", "microsoft_subject", existing_type=sa.String(255), nullable=False)
    op.drop_index("ux_operador_correo_local", table_name="operador")
    op.drop_column("operador", "fecha_creacion")
    op.drop_column("operador", "hash_contrasena")
