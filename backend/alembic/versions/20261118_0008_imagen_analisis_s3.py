"""Referencia al JPEG de inferencia en S3."""

import sqlalchemy as sa
from alembic import op

revision = "20261118_0008"
down_revision = "20261027_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("imagen", sa.Column("clave_analisis_s3", sa.String(1024), nullable=True))


def downgrade() -> None:
    op.drop_column("imagen", "clave_analisis_s3")
