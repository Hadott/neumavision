from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.database import get_session
from app.models import Deteccion, Imagen, Mision
from app.schemas import DashboardFinding


router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/findings", response_model=list[DashboardFinding])
def list_findings(session: Session = Depends(get_session)) -> list[DashboardFinding]:
    """Lista plana de hallazgos activos de todas las misiones.

    Mantiene compatibilidad con la estructura actual del esquema de datos
    (nombres en español), sin depender de columnas que no existen en la
    base de datos actual.
    """
    rows = session.exec(
        select(Deteccion, Imagen, Mision)
        .where(Deteccion.id_imagen == Imagen.id_imagen)
        .where(Imagen.id_mision == Mision.id_mision)
        .where(Deteccion.estado_revision != "rejected")
    ).all()

    findings: list[DashboardFinding] = []
    for detection, image, mission in rows:
        review_status = getattr(detection, "estado_revision", getattr(detection, "review_status", "pending"))
        repair_status = getattr(detection, "repair_status", "pending")
        created_at = getattr(detection, "created_at", None)
        if created_at is None:
            from datetime import datetime, timezone
            created_at = datetime.now(timezone.utc)

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
            )
        )
    return findings
