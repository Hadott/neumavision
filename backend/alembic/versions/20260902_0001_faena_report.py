"""Create the MVP schema, replacing the disposable prototype data."""

from datetime import datetime, timezone
from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260902_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEVELOPMENT_FAENA_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    existing_tables = set(sa.inspect(op.get_bind()).get_table_names())
    for table_name in ("report", "detection", "missionimage", "mission", "faena"):
        if table_name in existing_tables:
            op.drop_table(table_name)

    op.create_table(
        "faena",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_faena_email", "faena", ["email"], unique=True)
    op.create_index("ix_faena_name", "faena", ["name"], unique=False)
    op.bulk_insert(
        sa.table(
            "faena",
            sa.column("id", sa.String()),
            sa.column("name", sa.String()),
            sa.column("email", sa.String()),
            sa.column("password_hash", sa.String()),
            sa.column("created_at", sa.DateTime()),
        ),
        [{
            "id": DEVELOPMENT_FAENA_ID,
            "name": "Faena de desarrollo",
            "email": "desarrollo@neumavision.local",
            "password_hash": "authentication-not-implemented",
            "created_at": datetime.now(timezone.utc),
        }],
    )

    op.create_table(
        "mission",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("faena_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("segment", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["faena_id"], ["faena.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mission_faena_id", "mission", ["faena_id"], unique=False)
    op.create_index("ix_mission_name", "mission", ["name"], unique=False)
    op.create_index("ix_mission_status", "mission", ["status"], unique=False)

    op.create_table(
        "missionimage",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("mission_id", sa.String(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("stored_path", sa.String(), nullable=False),
        sa.Column("content_type", sa.String(length=80), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("altitude", sa.Float(), nullable=True),
        sa.Column("captured_at", sa.DateTime(), nullable=True),
        sa.Column("process_status", sa.String(length=30), nullable=False),
        sa.ForeignKeyConstraint(["mission_id"], ["mission.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_missionimage_mission_id", "missionimage", ["mission_id"], unique=False)
    op.create_index("ix_missionimage_process_status", "missionimage", ["process_status"], unique=False)

    op.create_table(
        "detection",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("image_id", sa.String(), nullable=False),
        sa.Column("label", sa.String(length=80), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("x", sa.Float(), nullable=False),
        sa.Column("y", sa.Float(), nullable=False),
        sa.Column("width", sa.Float(), nullable=False),
        sa.Column("height", sa.Float(), nullable=False),
        sa.Column("review_status", sa.String(length=30), nullable=False),
        sa.ForeignKeyConstraint(["image_id"], ["missionimage.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_detection_image_id", "detection", ["image_id"], unique=False)
    op.create_index("ix_detection_label", "detection", ["label"], unique=False)
    op.create_index("ix_detection_review_status", "detection", ["review_status"], unique=False)

    op.create_table(
        "report",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("mission_id", sa.String(), nullable=False),
        sa.Column("generated_at", sa.DateTime(), nullable=False),
        sa.Column("s3_object_key", sa.String(length=1024), nullable=False),
        sa.Column("finding_count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["mission_id"], ["mission.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("mission_id"),
    )
    op.create_index("ix_report_mission_id", "report", ["mission_id"], unique=True)


def downgrade() -> None:
    op.drop_table("report")
    op.drop_table("detection")
    op.drop_table("missionimage")
    op.drop_table("mission")
    op.drop_table("faena")
