import shutil
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, Response
from PIL import Image, ImageDraw
from sqlmodel import Session, delete, select

from app.config import settings
from app.database import get_session
from app.models import Deteccion, Imagen, Mision
from app.schemas import DetectionRead, DetectionRepairUpdate, DetectionReview, ImageRead, MissionRead, MissionSummary
from app.services.detector import get_detector
from app.services.metadata import extract_gps
from app.services.report import build_report
from app.services.storage import ALLOWED_CONTENT_TYPES, mission_directory, save_upload


router = APIRouter(prefix="/missions", tags=["missions"])


def serialize_detection(detection: Deteccion) -> DetectionRead:
    return DetectionRead(
        id=getattr(detection, "id_deteccion", getattr(detection, "id", "")),
        label=getattr(detection, "clase", getattr(detection, "label", "")),
        confidence=getattr(detection, "confianza", getattr(detection, "confidence", 0.0)),
        x=getattr(detection, "bbox_x", getattr(detection, "x", 0.0)),
        y=getattr(detection, "bbox_y", getattr(detection, "y", 0.0)),
        width=getattr(detection, "bbox_ancho", getattr(detection, "width", 0.0)),
        height=getattr(detection, "bbox_alto", getattr(detection, "height", 0.0)),
        review_status=getattr(detection, "estado_revision", getattr(detection, "review_status", "pending")),
        repair_status=getattr(detection, "estado_reparacion", getattr(detection, "repair_status", "pending")),
        created_at=getattr(detection, "created_at", datetime.now(timezone.utc)),
    )


def serialize_mission(session: Session, mission: Mision) -> MissionRead:
    images = session.exec(select(Imagen).where(Imagen.id_mision == mission.id_mision)).all()
    image_payload: list[ImageRead] = []
    for image in images:
        detections = session.exec(select(Deteccion).where(Deteccion.id_imagen == image.id_imagen)).all()
        image_payload.append(
            ImageRead(
                id=image.id_imagen,
                filename=image.nombre_archivo,
                width=image.ancho,
                height=image.alto,
                latitude=image.latitud,
                longitude=image.longitud,
                image_url=f"/api/v1/missions/{mission.id_mision}/images/{image.id_imagen}",
                detections=[serialize_detection(item) for item in detections],
            )
        )
    return MissionRead(
        id=mission.id_mision,
        name=mission.nombre,
        segment=mission.tramo,
        status=mission.estado,
        created_at=mission.fecha_creacion,
        images=image_payload,
    )


def require_mission(session: Session, mission_id: str) -> Mision:
    mission = session.exec(
        select(Mision).where(
            Mision.id_mision == mission_id,
            Mision.id_faena == settings.development_faena_id,
        )
    ).first()
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

    mission = Mision(id_faena=settings.development_faena_id, nombre=name, tramo=segment)
    session.add(mission)
    session.commit()
    session.refresh(mission)
    for upload in files:
        target = await save_upload(mission.id_mision, upload)
        try:
            with Image.open(target) as image:
                width, height = image.size
                latitude, longitude = extract_gps(image)
        except Exception as error:
            target.unlink(missing_ok=True)
            raise HTTPException(status_code=422, detail=f"Invalid image: {upload.filename}") from error
        session.add(
            Imagen(
                id_mision=mission.id_mision,
                nombre_archivo=upload.filename or target.name,
                ruta_almacenada=str(target),
                tipo_contenido=upload.content_type or "image/jpeg",
                ancho=width,
                alto=height,
                latitud=latitude,
                longitud=longitude,
            )
        )
    session.commit()
    return serialize_mission(session, mission)


@router.post("/demo", response_model=MissionRead, status_code=status.HTTP_201_CREATED)
def create_demo_mission(session: Session = Depends(get_session)) -> MissionRead:
    mission = Mision(
        id_faena=settings.development_faena_id,
        nombre="Misión demostrativa",
        tramo="Tramo A · km 2,4–3,0",
    )
    session.add(mission)
    session.commit()
    session.refresh(mission)
    directory = mission_directory(mission.id_mision)
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
            Imagen(
                id_mision=mission.id_mision,
                nombre_archivo=path.name,
                ruta_almacenada=str(path),
                tipo_contenido="image/jpeg",
                ancho=1200,
                alto=700,
                latitud=-27.38142 - index * 0.00031,
                longitud=-70.28761 + index * 0.00035,
            )
        )
    session.commit()
    return serialize_mission(session, mission)


@router.get("", response_model=list[MissionSummary])
def list_missions(session: Session = Depends(get_session)) -> list[MissionSummary]:
    missions = session.exec(
        select(Mision)
        .where(Mision.id_faena == settings.development_faena_id)
        .order_by(Mision.fecha_creacion.desc())
    ).all()
    summaries: list[MissionSummary] = []
    for mission in missions:
        images = session.exec(select(Imagen).where(Imagen.id_mision == mission.id_mision)).all()
        image_ids = [image.id_imagen for image in images]
        detections = (
            session.exec(select(Deteccion).where(Deteccion.id_imagen.in_(image_ids))).all()
            if image_ids
            else []
        )
        summaries.append(
            MissionSummary(
                id=mission.id_mision,
                name=mission.nombre,
                segment=mission.tramo,
                status=mission.estado,
                created_at=mission.fecha_creacion,
                image_count=len(images),
                detection_count=len(detections),
                pending_count=sum(1 for item in detections if item.estado_revision == "pending"),
                confirmed_count=sum(1 for item in detections if item.estado_revision == "confirmed"),
            )
        )
    return summaries


@router.get("/{mission_id}", response_model=MissionRead)
def get_mission(mission_id: str, session: Session = Depends(get_session)) -> MissionRead:
    return serialize_mission(session, require_mission(session, mission_id))


@router.delete("/{mission_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_mission(mission_id: str, session: Session = Depends(get_session)) -> Response:
    mission = require_mission(session, mission_id)
    images = session.exec(select(Imagen).where(Imagen.id_mision == mission.id_mision)).all()
    image_ids = [image.id_imagen for image in images]
    if image_ids:
        session.exec(delete(Deteccion).where(Deteccion.id_imagen.in_(image_ids)))
    session.exec(delete(Imagen).where(Imagen.id_mision == mission.id_mision))
    session.delete(mission)
    session.commit()
    shutil.rmtree(settings.upload_dir / mission_id, ignore_errors=True)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{mission_id}/detect", response_model=MissionRead)
def detect_mission(mission_id: str, session: Session = Depends(get_session)) -> MissionRead:
    mission = require_mission(session, mission_id)
    images = session.exec(select(Imagen).where(Imagen.id_mision == mission.id_mision)).all()
    image_ids = [image.id_imagen for image in images]
    if image_ids:
        session.exec(delete(Deteccion).where(Deteccion.id_imagen.in_(image_ids)))
    detector = get_detector()
    for image in images:
        for prediction in detector.predict(Path(image.ruta_almacenada)):
            session.add(
                Deteccion(
                    id_imagen=image.id_imagen,
                    clase=prediction.label,
                    confianza=prediction.confidence,
                    bbox_x=prediction.x,
                    bbox_y=prediction.y,
                    bbox_ancho=prediction.width,
                    bbox_alto=prediction.height,
                )
            )
    mission.estado = "review"
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
    detection = session.get(Deteccion, detection_id)
    image = session.get(Imagen, detection.id_imagen) if detection else None
    if not detection or not image or image.id_mision != mission_id:
        raise HTTPException(status_code=404, detail="Detection not found")
    detection.estado_revision = payload.review_status
    session.add(detection)
    session.commit()
    session.refresh(detection)
    return serialize_detection(detection)


@router.patch("/{mission_id}/detections/{detection_id}/repair", response_model=DetectionRead)
def update_repair_status(
    mission_id: str,
    detection_id: str,
    payload: DetectionRepairUpdate,
    session: Session = Depends(get_session),
) -> DetectionRead:
    # La confirmacion/revision de un hallazgo la realiza el modelo de IA; el estado de
    # reparacion es independiente y no depende de estado_revision.
    require_mission(session, mission_id)
    detection = session.get(Deteccion, detection_id)
    image = session.get(Imagen, detection.id_imagen) if detection else None
    if not detection or not image or image.id_mision != mission_id:
        raise HTTPException(status_code=404, detail="Detection not found")
    detection.estado_reparacion = payload.repair_status
    session.add(detection)
    session.commit()
    session.refresh(detection)
    return serialize_detection(detection)


@router.get("/{mission_id}/images/{image_id}")
def get_image(mission_id: str, image_id: str, session: Session = Depends(get_session)) -> FileResponse:
    require_mission(session, mission_id)
    image = session.get(Imagen, image_id)
    if not image or image.id_mision != mission_id:
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(
        image.ruta_almacenada,
        media_type=image.tipo_contenido,
        filename=image.nombre_archivo,
    )


@router.get("/{mission_id}/report")
def get_report(mission_id: str, session: Session = Depends(get_session)) -> Response:
    mission = require_mission(session, mission_id)
    images = list(session.exec(select(Imagen).where(Imagen.id_mision == mission.id_mision)).all())
    image_ids = [image.id_imagen for image in images]
    detections = (
        list(session.exec(select(Deteccion).where(Deteccion.id_imagen.in_(image_ids))).all())
        if image_ids
        else []
    )
    report = build_report(mission, images, detections)
    return Response(
        content=report,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="informe-{mission.id_mision[:8]}.pdf"'},
    )
