"""Rename the remaining faena columns to Spanish."""

from typing import Sequence

from alembic import op


revision: str = "20260902_0003"
down_revision: str | None = "20260902_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("faena", "email", new_column_name="correo")
    op.alter_column("faena", "password_hash", new_column_name="hash_contrasena")
    op.execute('ALTER INDEX "ix_faena_email" RENAME TO "ix_faena_correo"')
    op.execute('ALTER TABLE "faena" RENAME CONSTRAINT "faena_email_key" TO "faena_correo_key"')


def downgrade() -> None:
    op.execute('ALTER TABLE "faena" RENAME CONSTRAINT "faena_correo_key" TO "faena_email_key"')
    op.execute('ALTER INDEX "ix_faena_correo" RENAME TO "ix_faena_email"')
    op.alter_column("faena", "hash_contrasena", new_column_name="password_hash")
    op.alter_column("faena", "correo", new_column_name="email")
