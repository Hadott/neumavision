from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select

from app.database import get_session
from app.models import Deteccion, Faena, Imagen, Mision
from app.schemas import DashboardFinding
from app.services.auth import CurrentFaena, is_admin


router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/findings", response_model=list[DashboardFinding])
def list_findings(
    cuenta: CurrentFaena,
    faena_id: str | None = Query(default=None),
    session: Session = Depends(get_session),
) -> list[DashboardFinding]:
    """Lista plana de hallazgos activos de todas las misiones.

    Mantiene compatibilidad con la estructura actual del esquema de datos
    (nombres en español), sin depender de columnas que no existen en la
    base de datos actual.
    """
    query = (
        select(Deteccion, Imagen, Mision)
        .where(Deteccion.id_imagen == Imagen.id_imagen)
        .where(Imagen.id_mision == Mision.id_mision)
        .where(Deteccion.estado_revision != "rejected")
    )
    # Cada faena ve solo sus hallazgos; el administrador ve todos o filtra por faena.
    if not is_admin(cuenta):
        query = query.where(Mision.id_faena == cuenta.id_faena)
    elif faena_id:
        query = query.where(Mision.id_faena == faena_id)
    rows = session.exec(query).all()
    faena_names = {item.id_faena: item.nombre for item in session.exec(select(Faena)).all()}

    findings: list[DashboardFinding] = []
    for detection, image, mission in rows:
        # Registros antiguos pueden tener estos campos en NULL: se tratan como "pending".
        review_status = getattr(detection, "estado_revision", None) or "pending"
        repair_status = getattr(detection, "estado_reparacion", None) or "pending"
        # Fecha del hallazgo: captura de la imagen (EXIF) o, si no existe, creacion de la mision.
        created_at = image.fecha_captura or mission.fecha_creacion

        findings.append(
            DashboardFinding(
                id=getattr(detection, "id_deteccion", getattr(detection, "id", "")),
                label=getattr(detection, "clase", getattr(detection, "label", "")),
                confidence=getattr(detection, "confianza", getattr(detection, "confidence", 0.0)),
                review_status=review_status,
                repair_status=repair_status,
                created_at=created_at,
                x=getattr(detection, "bbox_x", getattr(detection, "x", 0.0)),
                y=getattr(detection, "bbox_y", getattr(detection, "y", 0.0)),
                width=getattr(detection, "bbox_ancho", getattr(detection, "width", 0.0)),
                height=getattr(detection, "bbox_alto", getattr(detection, "height", 0.0)),
                image_id=getattr(image, "id_imagen", getattr(image, "id", "")),
                image_filename=getattr(image, "nombre_archivo", getattr(image, "filename", "")),
                image_url=f"/api/v1/missions/{mission.id_mision}/images/{image.id_imagen}",
                latitude=getattr(image, "latitud", getattr(image, "latitude", None)),
                longitude=getattr(image, "longitud", getattr(image, "longitude", None)),
                mission_id=getattr(mission, "id_mision", getattr(mission, "id", "")),
                mission_name=getattr(mission, "nombre", getattr(mission, "name", "")),
                mission_segment=getattr(mission, "tramo", getattr(mission, "segment", "")),
                repaired_at=getattr(detection, "fecha_reparacion", None),
                faena_id=mission.id_faena,
                faena_name=faena_names.get(mission.id_faena, ""),
            )
        )
    return findings
