"""Separa las credenciales de las faenas y conserva las cuentas existentes."""

import sqlalchemy as sa
from alembic import op

revision = "20261125_0012"
down_revision = "20261125_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Older startup code may have already created an empty table from current metadata.
    op.execute("""
        DO $$
        BEGIN
            IF to_regclass('usuario') IS NOT NULL THEN
                LOCK TABLE usuario IN ACCESS EXCLUSIVE MODE;
                IF EXISTS (SELECT 1 FROM usuario) THEN
                    RAISE EXCEPTION 'La tabla usuario existente contiene datos';
                END IF;
                DROP TABLE usuario;
            END IF;
        END
        $$;
    """)
    op.rename_table("operador", "usuario")
    op.alter_column("usuario", "id_operador", new_column_name="id_usuario")
    op.execute("ALTER INDEX ix_operador_id_faena RENAME TO ix_usuario_id_faena")
    op.execute("ALTER INDEX ux_operador_correo_local RENAME TO ux_usuario_correo_local")
    op.add_column("usuario", sa.Column("rol", sa.String(20), server_default="operador", nullable=False))
    op.create_check_constraint(
        "ck_usuario_rol", "usuario", "rol IN ('admin', 'operador') AND (rol != 'admin' OR id_faena IS NULL)",
    )
    op.execute("""
        INSERT INTO usuario (id_usuario, nombre, correo, hash_contrasena, rol, fecha_creacion)
        SELECT id_faena, nombre, lower(trim(correo)), hash_contrasena, 'admin', fecha_creacion
          FROM faena WHERE rol = 'admin'
    """)
    op.execute("""
        DELETE FROM faena WHERE rol = 'admin'
          AND NOT EXISTS (SELECT 1 FROM mision WHERE mision.id_faena = faena.id_faena)
          AND NOT EXISTS (SELECT 1 FROM usuario WHERE usuario.id_faena = faena.id_faena)
    """)
    for column in ("microsoft_subject", "rol", "hash_contrasena", "correo"):
        op.drop_column("faena", column)


def downgrade() -> None:
    raise RuntimeError("Los correos y hashes históricos de faena solo se recuperan desde una copia previa.")
