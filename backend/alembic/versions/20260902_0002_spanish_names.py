"""Rename application tables and columns to Spanish."""

from typing import Sequence

from alembic import op


revision: str = "20260902_0002"
down_revision: str | None = "20260902_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _rename_columns(table_name: str, names: dict[str, str]) -> None:
    for old_name, new_name in names.items():
        op.alter_column(table_name, old_name, new_column_name=new_name)


def upgrade() -> None:
    op.rename_table("mission", "mision")
    op.rename_table("missionimage", "imagen")
    op.rename_table("detection", "deteccion")
    op.rename_table("report", "informe")

    _rename_columns("faena", {
        "id": "id_faena",
        "name": "nombre",
        "created_at": "fecha_creacion",
    })
    _rename_columns("mision", {
        "id": "id_mision",
        "faena_id": "id_faena",
        "name": "nombre",
        "segment": "tramo",
        "status": "estado",
        "created_at": "fecha_creacion",
    })
    _rename_columns("imagen", {
        "id": "id_imagen",
        "mission_id": "id_mision",
        "filename": "nombre_archivo",
        "stored_path": "ruta_almacenada",
        "content_type": "tipo_contenido",
        "width": "ancho",
        "height": "alto",
        "latitude": "latitud",
        "longitude": "longitud",
        "altitude": "altitud",
        "captured_at": "fecha_captura",
        "process_status": "estado_proceso",
    })
    _rename_columns("deteccion", {
        "id": "id_deteccion",
        "image_id": "id_imagen",
        "label": "clase",
        "confidence": "confianza",
        "x": "bbox_x",
        "y": "bbox_y",
        "width": "bbox_ancho",
        "height": "bbox_alto",
        "review_status": "estado_revision",
    })
    _rename_columns("informe", {
        "id": "id_informe",
        "mission_id": "id_mision",
        "generated_at": "fecha_generacion",
        "s3_object_key": "clave_objeto_s3",
        "finding_count": "total_hallazgos",
    })

    index_renames = {
        "ix_faena_name": "ix_faena_nombre",
        "ix_mission_faena_id": "ix_mision_id_faena",
        "ix_mission_name": "ix_mision_nombre",
        "ix_mission_status": "ix_mision_estado",
        "ix_missionimage_mission_id": "ix_imagen_id_mision",
        "ix_missionimage_process_status": "ix_imagen_estado_proceso",
        "ix_detection_image_id": "ix_deteccion_id_imagen",
        "ix_detection_label": "ix_deteccion_clase",
        "ix_detection_review_status": "ix_deteccion_estado_revision",
        "ix_report_mission_id": "ix_informe_id_mision",
    }
    for old_name, new_name in index_renames.items():
        op.execute(f'ALTER INDEX "{old_name}" RENAME TO "{new_name}"')

    constraint_renames = {
        "mision": {
            "mission_pkey": "mision_pkey",
            "mission_faena_id_fkey": "mision_id_faena_fkey",
        },
        "imagen": {
            "missionimage_pkey": "imagen_pkey",
            "missionimage_mission_id_fkey": "imagen_id_mision_fkey",
        },
        "deteccion": {
            "detection_pkey": "deteccion_pkey",
            "detection_image_id_fkey": "deteccion_id_imagen_fkey",
        },
        "informe": {
            "report_pkey": "informe_pkey",
            "report_mission_id_fkey": "informe_id_mision_fkey",
            "report_mission_id_key": "informe_id_mision_key",
        },
    }
    for table_name, constraints in constraint_renames.items():
        for old_name, new_name in constraints.items():
            op.execute(
                f'ALTER TABLE "{table_name}" RENAME CONSTRAINT "{old_name}" TO "{new_name}"'
            )


def downgrade() -> None:
    raise NotImplementedError("Spanish database names are the new canonical schema")
