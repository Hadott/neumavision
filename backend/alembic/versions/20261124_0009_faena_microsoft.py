"""Identidad de Microsoft asociada a una faena."""

import sqlalchemy as sa
from alembic import op

revision = "20261124_0009"
down_revision = "20261118_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("faena", sa.Column("microsoft_subject", sa.String(255), nullable=True))
    op.create_unique_constraint("uq_faena_microsoft_subject", "faena", ["microsoft_subject"])


def downgrade() -> None:
    op.drop_constraint("uq_faena_microsoft_subject", "faena", type_="unique")
    op.drop_column("faena", "microsoft_subject")
