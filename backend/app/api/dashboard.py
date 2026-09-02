from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.database import get_session
from app.models import Detection, Mission, MissionImage
from app.schemas import DashboardFinding


router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/findings", response_model=list[DashboardFinding])
def list_findings(session: Session = Depends(get_session)) -> list[DashboardFinding]:
    """Flat list of active findings (rejected ones excluded) across every
    mission, joined with their image and mission context, for the
    cross-mission map/filters dashboard."""
    rows = session.exec(
        select(Detection, MissionImage, Mission)
        .where(Detection.image_id == MissionImage.id)
        .where(MissionImage.mission_id == Mission.id)
        .where(Detection.review_status != "rejected")
        .order_by(Detection.created_at.desc())
    ).all()
    findings: list[DashboardFinding] = []
    for detection, image, mission in rows:
        findings.append(
            DashboardFinding(
                id=detection.id,
                label=detection.label,
                confidence=detection.confidence,
                review_status=detection.review_status,
                repair_status=detection.repair_status,
                created_at=detection.created_at,
                x=detection.x,
                y=detection.y,
                width=detection.width,
                height=detection.height,
                image_id=image.id,
                image_filename=image.filename,
                image_url=f"/api/v1/missions/{mission.id}/images/{image.id}",
                latitude=image.latitude,
                longitude=image.longitude,
                mission_id=mission.id,
                mission_name=mission.name,
                mission_segment=mission.segment,
            )
        )
    return findings
