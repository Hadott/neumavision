import shutil
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, Response
from PIL import Image, ImageDraw
from sqlmodel import Session, delete, select

from app.config import settings
from app.database import get_session
from app.models import Detection, Mission, MissionImage
from app.schemas import DetectionRead, DetectionReview, ImageRead, MissionRead, MissionSummary
from app.services.detector import get_detector
from app.services.metadata import extract_gps
from app.services.report import build_report
from app.services.storage import ALLOWED_CONTENT_TYPES, mission_directory, save_upload


router = APIRouter(prefix="/missions", tags=["missions"])


def serialize_mission(session: Session, mission: Mission) -> MissionRead:
    images = session.exec(select(MissionImage).where(MissionImage.mission_id == mission.id)).all()
    image_payload: list[ImageRead] = []
    for image in images:
        detections = session.exec(select(Detection).where(Detection.image_id == image.id)).all()
        image_payload.append(
            ImageRead(
                id=image.id,
                filename=image.filename,
                width=image.width,
                height=image.height,
                latitude=image.latitude,
                longitude=image.longitude,
                image_url=f"/api/v1/missions/{mission.id}/images/{image.id}",
                detections=[DetectionRead.model_validate(item, from_attributes=True) for item in detections],
            )
        )
    return MissionRead(
        id=mission.id,
        name=mission.name,
        segment=mission.segment,
        status=mission.status,
        created_at=mission.created_at,
        images=image_payload,
    )


def require_mission(session: Session, mission_id: str) -> Mission:
    mission = session.get(Mission, mission_id)
    if not mission:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mission not found")
    return mission


@router.post("", response_model=MissionRead, status_code=status.HTTP_201_CREATED)
async def create_mission(
    name: str = Form(..., min_length=2, max_length=120),
    segment: str = Form("Sin tramo", max_length=120),
    files: list[UploadFile] = File(...),
    session: Session = Depends(get_session),
) -> MissionRead:
    if not files:
        raise HTTPException(status_code=400, detail="Upload at least one image")
    invalid = [file.filename for file in files if file.content_type not in ALLOWED_CONTENT_TYPES]
    if invalid:
        raise HTTPException(status_code=415, detail=f"Unsupported files: {', '.join(str(item) for item in invalid)}")

    mission = Mission(name=name, segment=segment)
    session.add(mission)
    session.commit()
    session.refresh(mission)
    for upload in files:
        target = await save_upload(mission.id, upload)
        try:
            with Image.open(target) as image:
                width, height = image.size
                latitude, longitude = extract_gps(image)
        except Exception as error:
            target.unlink(missing_ok=True)
            raise HTTPException(status_code=422, detail=f"Invalid image: {upload.filename}") from error
        session.add(
            MissionImage(
                mission_id=mission.id,
                filename=upload.filename or target.name,
                stored_path=str(target),
                content_type=upload.content_type or "image/jpeg",
                width=width,
                height=height,
                latitude=latitude,
                longitude=longitude,
            )
        )
    session.commit()
    return serialize_mission(session, mission)


@router.post("/demo", response_model=MissionRead, status_code=status.HTTP_201_CREATED)
def create_demo_mission(session: Session = Depends(get_session)) -> MissionRead:
    mission = Mission(name="Misión demostrativa", segment="Tramo A · km 2,4–3,0")
    session.add(mission)
    session.commit()
    session.refresh(mission)
    directory = mission_directory(mission.id)
    for index in range(4):
        image = Image.new("RGB", (1200, 700), (138, 169, 179))
        draw = ImageDraw.Draw(image)
        draw.polygon([(0, 100), (210, 55), (430, 90), (720, 35), (1200, 75), (1200, 0), (0, 0)], fill=(91, 82, 68))
        draw.polygon([(0, 700), (160 + index * 25, 390), (520, 270), (1200, 310 - index * 12), (1200, 700)], fill=(121, 104, 82))
        draw.line([(525, 275), (660, 700)], fill=(176, 155, 120), width=10)
        draw.ellipse((230 + index * 55, 430, 390 + index * 55, 485), fill=(70, 62, 51))
        draw.ellipse((810 - index * 35, 465, 875 - index * 35, 515), fill=(65, 58, 48))
        path = directory / f"DJI_DEMO_{index + 1:04}.jpg"
        image.save(path, "JPEG", quality=88)
        session.add(
            MissionImage(
                mission_id=mission.id,
                filename=path.name,
                stored_path=str(path),
                content_type="image/jpeg",
                width=1200,
                height=700,
                latitude=-27.38142 - index * 0.00031,
                longitude=-70.28761 + index * 0.00035,
            )
        )
    session.commit()
    return serialize_mission(session, mission)


@router.get("", response_model=list[MissionSummary])
def list_missions(session: Session = Depends(get_session)) -> list[MissionSummary]:
    missions = session.exec(select(Mission).order_by(Mission.created_at.desc())).all()
    summaries: list[MissionSummary] = []
    for mission in missions:
        images = session.exec(select(MissionImage).where(MissionImage.mission_id == mission.id)).all()
        image_ids = [image.id for image in images]
        detections = (
            session.exec(select(Detection).where(Detection.image_id.in_(image_ids))).all()
            if image_ids
            else []
        )
        summaries.append(
            MissionSummary(
                id=mission.id,
                name=mission.name,
                segment=mission.segment,
                status=mission.status,
                created_at=mission.created_at,
                image_count=len(images),
                detection_count=len(detections),
                pending_count=sum(1 for item in detections if item.review_status == "pending"),
                confirmed_count=sum(1 for item in detections if item.review_status == "confirmed"),
            )
        )
    return summaries


@router.get("/{mission_id}", response_model=MissionRead)
def get_mission(mission_id: str, session: Session = Depends(get_session)) -> MissionRead:
    return serialize_mission(session, require_mission(session, mission_id))


@router.delete("/{mission_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_mission(mission_id: str, session: Session = Depends(get_session)) -> Response:
    mission = require_mission(session, mission_id)
    images = session.exec(select(MissionImage).where(MissionImage.mission_id == mission.id)).all()
    image_ids = [image.id for image in images]
    if image_ids:
        session.exec(delete(Detection).where(Detection.image_id.in_(image_ids)))
    session.exec(delete(MissionImage).where(MissionImage.mission_id == mission.id))
    session.delete(mission)
    session.commit()
    shutil.rmtree(settings.upload_dir / mission_id, ignore_errors=True)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{mission_id}/detect", response_model=MissionRead)
def detect_mission(mission_id: str, session: Session = Depends(get_session)) -> MissionRead:
    mission = require_mission(session, mission_id)
    images = session.exec(select(MissionImage).where(MissionImage.mission_id == mission.id)).all()
    image_ids = [image.id for image in images]
    if image_ids:
        session.exec(delete(Detection).where(Detection.image_id.in_(image_ids)))
    detector = get_detector()
    for image in images:
        for prediction in detector.predict(Path(image.stored_path)):
            session.add(Detection(image_id=image.id, **prediction.__dict__))
    mission.status = "review"
    session.add(mission)
    session.commit()
    session.refresh(mission)
    return serialize_mission(session, mission)


@router.patch("/{mission_id}/detections/{detection_id}", response_model=DetectionRead)
def review_detection(
    mission_id: str,
    detection_id: str,
    payload: DetectionReview,
    session: Session = Depends(get_session),
) -> DetectionRead:
    require_mission(session, mission_id)
    detection = session.get(Detection, detection_id)
    if not detection:
        raise HTTPException(status_code=404, detail="Detection not found")
    detection.review_status = payload.review_status
    session.add(detection)
    session.commit()
    session.refresh(detection)
    return DetectionRead.model_validate(detection, from_attributes=True)


@router.get("/{mission_id}/images/{image_id}")
def get_image(mission_id: str, image_id: str, session: Session = Depends(get_session)) -> FileResponse:
    require_mission(session, mission_id)
    image = session.get(MissionImage, image_id)
    if not image or image.mission_id != mission_id:
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(image.stored_path, media_type=image.content_type, filename=image.filename)


@router.get("/{mission_id}/report")
def get_report(mission_id: str, session: Session = Depends(get_session)) -> Response:
    mission = require_mission(session, mission_id)
    images = list(session.exec(select(MissionImage).where(MissionImage.mission_id == mission.id)).all())
    image_ids = [image.id for image in images]
    detections = list(session.exec(select(Detection).where(Detection.image_id.in_(image_ids))).all()) if image_ids else []
    report = build_report(mission, images, detections)
    return Response(
        content=report,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="informe-{mission.id[:8]}.pdf"'},
    )
