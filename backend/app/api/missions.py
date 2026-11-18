import json
import shutil
from contextlib import ExitStack, nullcontext
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock
from time import monotonic

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, Response
from PIL import Image, ImageDraw
from sqlmodel import Session, delete, select
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.database import get_session
from app.models import Deteccion, Faena, Imagen, Informe, Mision
from app.schemas import (
    DetectionRead,
    DetectionProgressRead,
    DetectionRepairUpdate,
    DetectionReview,
    ImageCriticalityUpdate,
    ImageRead,
    MissionRead,
    RoadWidthRead,
    MissionSummary,
)
from app.services.auth import CurrentFaena, is_admin
from app.services.detector import DetectorError, OFF_ROAD_LABEL, RemoteDetector, get_detector, overlay_path, width_paths
from app.services.jade import JadeUnavailable, MissionAlreadyRunning, jade
from app.services.metadata import extract_gps
from app.services.report import build_report
from app.services.storage import (
    ALLOWED_CONTENT_TYPES, AnalysisStorageError, mission_directory, original_key, read_analysis,
    save_upload, store_analysis, store_object, store_original, use_original,
)


router = APIRouter(prefix="/missions", tags=["missions"])
active_detection: dict[str, DetectionProgressRead] = {}
detection_lock = Lock()


def serialize_detection(detection: Deteccion) -> DetectionRead:
    return DetectionRead(
        id=getattr(detection, "id_deteccion", getattr(detection, "id", "")),
        label=getattr(detection, "clase", getattr(detection, "label", "")),
        confidence=getattr(detection, "confianza", getattr(detection, "confidence", 0.0)),
        x=getattr(detection, "bbox_x", getattr(detection, "x", 0.0)),
        y=getattr(detection, "bbox_y", getattr(detection, "y", 0.0)),
        width=getattr(detection, "bbox_ancho", getattr(detection, "width", 0.0)),
        height=getattr(detection, "bbox_alto", getattr(detection, "height", 0.0)),
        review_status=getattr(detection, "estado_revision", None) or "pending",
        repair_status=getattr(detection, "estado_reparacion", None) or "pending",
        created_at=getattr(detection, "created_at", datetime.now(timezone.utc)),
    )


def read_road_width(image: Imagen) -> RoadWidthRead | None:
    """Lee el analisis de ancho guardado junto a la imagen por el detector NeumaVision."""
    _, json_path = width_paths(Path(image.ruta_almacenada))
    if not json_path.exists():
        return None
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    number = lambda value: float(value) if value not in ("", None) else None
    return RoadWidthRead(
        estado=str(data.get("estado", "Sin medición")),
        ancho_min_m=number(data.get("ancho_min_p10_m")),
        ancho_mediano_m=number(data.get("ancho_mediano_m")),
        gsd_cm_px=number(data.get("gsd_cm_px")),
        fuente_gsd=str(data.get("fuente_gsd", "")),
        eje_medible_pct=float(data.get("eje_medible_pct") or 0),
        confianza_pista=number(data.get("confianza_pista")),
        clase_pista=str(data.get("clase_pista") or "") or None,
    )


def width_version(image: Imagen) -> int:
    """Version del analisis de ancho (fecha del archivo). Va en la URL para que el navegador
    no muestre una imagen antigua guardada en cache despues de volver a ejecutar la deteccion."""
    overlay_path, _ = width_paths(Path(image.ruta_almacenada))
    try:
        return int(overlay_path.stat().st_mtime)
    except OSError:
        return 0


def serialize_image(session: Session, mission_id: str, image: Imagen) -> ImageRead:
    detections = session.exec(select(Deteccion).where(Deteccion.id_imagen == image.id_imagen)).all()
    road_width = read_road_width(image)
    return ImageRead(
        id=image.id_imagen,
        filename=image.nombre_archivo,
        width=image.ancho,
        height=image.alto,
        latitude=image.latitud,
        longitude=image.longitud,
        image_url=f"/api/v1/missions/{mission_id}/images/{image.id_imagen}",
        analysis_url=(f"/api/v1/missions/{mission_id}/images/{image.id_imagen}?analysis=true"
                      if image.clave_analisis_s3 or overlay_path(Path(image.ruta_almacenada)).is_file() else None),
        detections=[serialize_detection(item) for item in detections],
        criticidad_manual=image.criticidad_manual,
        road_width=road_width,
        road_width_url=(
            f"/api/v1/missions/{mission_id}/images/{image.id_imagen}/ancho?v={width_version(image)}"
            if road_width
            else None
        ),
    )


def serialize_mission(session: Session, mission: Mision) -> MissionRead:
    images = session.exec(select(Imagen).where(Imagen.id_mision == mission.id_mision)).all()
    image_payload = [serialize_image(session, mission.id_mision, image) for image in images]
    return MissionRead(
        id=mission.id_mision,
        name=mission.nombre,
        segment=mission.tramo,
        status=mission.estado,
        created_at=mission.fecha_creacion,
        images=image_payload,
    )


def require_mission(session: Session, mission_id: str, cuenta: Faena) -> Mision:
    """Busca la mision; una cuenta de faena solo accede a sus propias misiones."""
    query = select(Mision).where(Mision.id_mision == mission_id)
    if not is_admin(cuenta):
        query = query.where(Mision.id_faena == cuenta.id_faena)
    mission = session.exec(query).first()
    if not mission:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mission not found")
    return mission


def target_faena_id(session: Session, cuenta: Faena, faena_id: str | None) -> str:
    """Faena a la que se asigna una mision nueva. El administrador debe indicarla;
    una cuenta de faena siempre crea misiones propias."""
    if not is_admin(cuenta):
        return cuenta.id_faena
    if not faena_id:
        raise HTTPException(status_code=400, detail="Selecciona la faena a la que pertenece la misión.")
    if session.get(Faena, faena_id) is None:
        raise HTTPException(status_code=404, detail="Faena no encontrada.")
    return faena_id


@router.post("", response_model=MissionRead, status_code=status.HTTP_201_CREATED)
async def create_mission(
    cuenta: CurrentFaena,
    name: str = Form(..., min_length=2, max_length=120),
    segment: str = Form("Sin tramo", max_length=120),
    files: list[UploadFile] = File(...),
    faena_id: str | None = Form(None),
    session: Session = Depends(get_session),
) -> MissionRead:
    if not files:
        raise HTTPException(status_code=400, detail="Upload at least one image")
    invalid = [file.filename for file in files if file.content_type not in ALLOWED_CONTENT_TYPES]
    if invalid:
        raise HTTPException(status_code=415, detail=f"Unsupported files: {', '.join(str(item) for item in invalid)}")

    mission = Mision(id_faena=target_faena_id(session, cuenta, faena_id), nombre=name, tramo=segment)
    session.add(mission)
    originals = []
    try:
        for upload in files:
            target = await save_upload(mission.id_mision, upload)
            try:
                with Image.open(target) as image:
                    width, height = image.size
                    latitude, longitude = extract_gps(image)
            except (OSError, ValueError, Image.DecompressionBombError) as error:
                raise HTTPException(status_code=422, detail=f"Invalid image: {upload.filename}") from error
            record = Imagen(
                id_mision=mission.id_mision,
                nombre_archivo=upload.filename or target.name,
                ruta_almacenada=str(target),
                tipo_contenido=upload.content_type or "image/jpeg",
                ancho=width,
                alto=height,
                latitud=latitude,
                longitud=longitude,
            )
            originals.append((target, record.tipo_contenido))
            session.add(record)
        if settings.analysis_s3_bucket:
            for target, content_type in originals:
                await run_in_threadpool(store_original, mission.id_mision, target, content_type)
                target.unlink()
        session.commit()
    except (HTTPException, AnalysisStorageError, SQLAlchemyError, OSError) as error:
        session.rollback()
        shutil.rmtree(settings.upload_dir / mission.id_mision, ignore_errors=True)
        if isinstance(error, HTTPException):
            raise
        raise HTTPException(503, detail="No se pudieron guardar las imágenes originales.") from error
    return serialize_mission(session, mission)


@router.post("/demo", response_model=MissionRead, status_code=status.HTTP_201_CREATED)
def create_demo_mission(cuenta: CurrentFaena, session: Session = Depends(get_session)) -> MissionRead:
    mission = Mision(
        id_faena=cuenta.id_faena,
        nombre="Misión demostrativa",
        tramo="Tramo A · km 2,4–3,0",
    )
    session.add(mission)
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
        if settings.analysis_s3_bucket:
            try:
                store_original(mission.id_mision, path, "image/jpeg")
                path.unlink()
            except (AnalysisStorageError, OSError) as error:
                session.rollback()
                shutil.rmtree(directory, ignore_errors=True)
                raise HTTPException(503, detail="No se pudieron guardar las imágenes originales.") from error
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
def list_missions(
    cuenta: CurrentFaena,
    faena_id: str | None = Query(default=None),
    session: Session = Depends(get_session),
) -> list[MissionSummary]:
    query = select(Mision).order_by(Mision.fecha_creacion.desc())
    if not is_admin(cuenta):
        query = query.where(Mision.id_faena == cuenta.id_faena)
    elif faena_id:
        query = query.where(Mision.id_faena == faena_id)
    missions = session.exec(query).all()
    faena_names = {item.id_faena: item.nombre for item in session.exec(select(Faena)).all()}
    summaries: list[MissionSummary] = []
    for mission in missions:
        images = session.exec(select(Imagen).where(Imagen.id_mision == mission.id_mision)).all()
        image_ids = [image.id_imagen for image in images]
        detections = (
            session.exec(
                select(Deteccion)
                .where(Deteccion.id_imagen.in_(image_ids))
                .where(Deteccion.clase != OFF_ROAD_LABEL)
            ).all()
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
                criticidad_critico_count=sum(1 for item in images if item.criticidad_manual == "critico"),
                criticidad_moderado_count=sum(1 for item in images if item.criticidad_manual == "moderado"),
                criticidad_optimo_count=sum(1 for item in images if item.criticidad_manual == "optimo"),
                faena_id=mission.id_faena,
                faena_name=faena_names.get(mission.id_faena, ""),
            )
        )
    return summaries


@router.get("/{mission_id}", response_model=MissionRead)
def get_mission(mission_id: str, cuenta: CurrentFaena, session: Session = Depends(get_session)) -> MissionRead:
    return serialize_mission(session, require_mission(session, mission_id, cuenta))


@router.delete("/{mission_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_mission(mission_id: str, cuenta: CurrentFaena, session: Session = Depends(get_session)) -> Response:
    mission = require_mission(session, mission_id, cuenta)
    images = session.exec(select(Imagen).where(Imagen.id_mision == mission.id_mision)).all()
    image_ids = [image.id_imagen for image in images]
    if image_ids:
        session.exec(delete(Deteccion).where(Deteccion.id_imagen.in_(image_ids)))
    session.exec(delete(Imagen).where(Imagen.id_mision == mission.id_mision))
    session.exec(delete(Informe).where(Informe.id_mision == mission.id_mision))
    session.delete(mission)
    session.commit()
    shutil.rmtree(settings.upload_dir / mission_id, ignore_errors=True)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{mission_id}/detect/progress", response_model=DetectionProgressRead | None)
def detection_progress(mission_id: str, cuenta: CurrentFaena, session: Session = Depends(get_session)):
    require_mission(session, mission_id, cuenta)
    with detection_lock:
        return active_detection.get(mission_id)


@router.post("/{mission_id}/detect", response_model=MissionRead)
def detect_mission(mission_id: str, cuenta: CurrentFaena, session: Session = Depends(get_session)) -> MissionRead:
    mission = require_mission(session, mission_id, cuenta)
    images = session.exec(select(Imagen).where(Imagen.id_mision == mission.id_mision)).all()
    image_ids = [image.id_imagen for image in images]
    if not images:
        raise HTTPException(422, detail="La misión no tiene imágenes.")
    detector = get_detector()
    managed = bool(settings.jade_instance_id) and isinstance(detector, RemoteDetector)
    lease = jade.mission(mission_id) if managed else nullcontext()
    total = len(images)
    with detection_lock:
        if mission_id in active_detection:
            raise HTTPException(409, detail="La misión ya se está procesando.")
        active_detection[mission_id] = DetectionProgressRead(
            phase="starting" if managed else "processing", completed=0, total=total,
        )
    try:
        with lease, TemporaryDirectory() as work_dir:
            started = monotonic()
            with detection_lock:
                active_detection[mission_id] = DetectionProgressRead(phase="processing", completed=0, total=total)
            predictions = []
            for completed, image in enumerate(images, start=1):
                with use_original(mission_id, Path(image.ruta_almacenada)) as path:
                    if isinstance(detector, RemoteDetector) and settings.analysis_s3_bucket:
                        overlay = Path(work_dir) / f"{image.id_imagen}.jpg"
                        findings = detector.predict(path, output_path=overlay)
                        image.clave_analisis_s3 = store_analysis(mission_id, image.id_imagen, overlay)
                    else:
                        findings = detector.predict(path)
                predictions.append((image, findings))
                with detection_lock:
                    active_detection[mission_id] = DetectionProgressRead(
                        phase="saving" if completed == total else "processing",
                        completed=completed, total=total,
                        estimated_remaining_seconds=(
                            (monotonic() - started) / completed * (total - completed)
                            if completed < total else None
                        ),
                    )
            session.exec(delete(Deteccion).where(Deteccion.id_imagen.in_(image_ids)))
            for image, findings in predictions:
                for prediction in findings:
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
                image.estado_proceso = "completed"
                session.add(image)
            mission.estado = "review"
            session.add(mission)
            session.commit()
        session.refresh(mission)
        return serialize_mission(session, mission)
    except MissionAlreadyRunning as error:
        raise HTTPException(409, detail=str(error)) from error
    except (JadeUnavailable, AnalysisStorageError) as error:
        session.rollback()
        raise HTTPException(503, detail=str(error)) from error
    except DetectorError as error:
        session.rollback()
        raise HTTPException(502, detail=str(error)) from error
    except SQLAlchemyError as error:
        session.rollback()
        raise HTTPException(503, detail="No se pudieron guardar los hallazgos") from error
    finally:
        with detection_lock:
            active_detection.pop(mission_id, None)


@router.patch("/{mission_id}/detections/{detection_id}", response_model=DetectionRead)
def review_detection(
    mission_id: str,
    detection_id: str,
    payload: DetectionReview,
    cuenta: CurrentFaena,
    session: Session = Depends(get_session),
) -> DetectionRead:
    require_mission(session, mission_id, cuenta)
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
    cuenta: CurrentFaena,
    session: Session = Depends(get_session),
) -> DetectionRead:
    # La confirmacion/revision de un hallazgo la realiza el modelo de IA; el estado de
    # reparacion es independiente y no depende de estado_revision.
    require_mission(session, mission_id, cuenta)
    detection = session.get(Deteccion, detection_id)
    image = session.get(Imagen, detection.id_imagen) if detection else None
    if not detection or not image or image.id_mision != mission_id:
        raise HTTPException(status_code=404, detail="Detection not found")
    if payload.repair_status != detection.estado_reparacion:
        detection.fecha_reparacion = (
            datetime.now(timezone.utc) if payload.repair_status == "repaired" else None
        )
    detection.estado_reparacion = payload.repair_status
    session.add(detection)
    session.commit()
    session.refresh(detection)
    return serialize_detection(detection)


@router.patch("/{mission_id}/images/{image_id}/criticidad", response_model=ImageRead)
def update_image_criticality(
    mission_id: str,
    image_id: str,
    payload: ImageCriticalityUpdate,
    cuenta: CurrentFaena,
    session: Session = Depends(get_session),
) -> ImageRead:
    """Clasificacion manual de criticidad por imagen (semaforo), asignada por el revisor.
    Es independiente de la criticidad automatica por confianza que usa el Dashboard."""
    mission = require_mission(session, mission_id, cuenta)
    image = session.get(Imagen, image_id)
    if not image or image.id_mision != mission.id_mision:
        raise HTTPException(status_code=404, detail="Image not found")
    image.criticidad_manual = payload.criticidad_manual
    session.add(image)
    if payload.criticidad_manual is not None:
        # Asignar una criticidad significa que el revisor ya evaluo la imagen: confirma
        # automaticamente los hallazgos que seguian pendientes de revision.
        detections = session.exec(select(Deteccion).where(Deteccion.id_imagen == image.id_imagen)).all()
        for detection in detections:
            if detection.estado_revision == "pending":
                detection.estado_revision = "confirmed"
                session.add(detection)
    session.commit()
    session.refresh(image)
    return serialize_image(session, mission.id_mision, image)


@router.get("/{mission_id}/images/{image_id}")
def get_image(mission_id: str, image_id: str, cuenta: CurrentFaena,
              analysis: bool = False, session: Session = Depends(get_session)) -> Response:
    require_mission(session, mission_id, cuenta)
    image = session.get(Imagen, image_id)
    if not image or image.id_mision != mission_id:
        raise HTTPException(status_code=404, detail="Image not found")
    if analysis and image.clave_analisis_s3:
        try:
            return Response(read_analysis(image.clave_analisis_s3), media_type="image/jpeg")
        except AnalysisStorageError as error:
            raise HTTPException(503, detail=str(error)) from error
    path = overlay_path(Path(image.ruta_almacenada)) if analysis else Path(image.ruta_almacenada)
    if not analysis and settings.analysis_s3_bucket:
        try:
            return Response(read_analysis(original_key(mission_id, path)), media_type=image.tipo_contenido)
        except AnalysisStorageError as error:
            if not path.is_file():
                raise HTTPException(503, detail=str(error)) from error
    if not path.is_file():
        raise HTTPException(404, detail="Image not found")
    return FileResponse(
        path,
        media_type="image/jpeg" if analysis else image.tipo_contenido,
        filename=image.nombre_archivo,
    )


@router.get("/{mission_id}/images/{image_id}/ancho")
def get_road_width_image(
    mission_id: str, image_id: str, cuenta: CurrentFaena, session: Session = Depends(get_session)
) -> FileResponse:
    """Imagen anotada con el ancho de pista (eje, lineas transversales y semaforo)."""
    require_mission(session, mission_id, cuenta)
    image = session.get(Imagen, image_id)
    if not image or image.id_mision != mission_id:
        raise HTTPException(status_code=404, detail="Image not found")
    overlay_path, _ = width_paths(Path(image.ruta_almacenada))
    if not overlay_path.exists():
        raise HTTPException(status_code=404, detail="Esta imagen no tiene análisis de ancho")
    return FileResponse(overlay_path, media_type="image/jpeg")


@router.get("/{mission_id}/report")
def get_report(
    mission_id: str,
    cuenta: CurrentFaena,
    vista: str = Query(default="ambas", pattern="^(ambas|segmentacion|rocas)$"),
    session: Session = Depends(get_session),
) -> Response:
    """vista: tipo de imagen de cada ficha, igual a la opcion elegida en Revision."""
    mission = require_mission(session, mission_id, cuenta)
    images = list(session.exec(select(Imagen).where(Imagen.id_mision == mission.id_mision)).all())
    image_ids = [image.id_imagen for image in images]
    detections = (
        list(session.exec(select(Deteccion).where(Deteccion.id_imagen.in_(image_ids))).all())
        if image_ids
        else []
    )
    # El informe solo incluye rocas sobre la pista y las imagenes que tienen al menos una.
    off_road = [item for item in detections if item.clase == OFF_ROAD_LABEL]
    detections = [item for item in detections if item.clase != OFF_ROAD_LABEL]
    with_findings = {item.id_imagen for item in detections if item.estado_revision != "rejected"}
    images = [image for image in images if image.id_imagen in with_findings]
    try:
        with ExitStack() as originals:
            for image in images:
                originals.enter_context(use_original(mission_id, Path(image.ruta_almacenada)))
            # Las rocas fuera de la pista se dibujan como referencia.
            report = build_report(mission, images, detections, context_detections=off_road, view=vista)
    except (AnalysisStorageError, OSError) as error:
        raise HTTPException(503, detail="No se pudieron leer los originales del informe.") from error
    if settings.analysis_s3_bucket:
        try:
            session.exec(select(Mision).where(Mision.id_mision == mission_id).with_for_update()).one()
            stored = session.exec(select(Informe).where(Informe.id_mision == mission_id)).first()
            key = f"reports/{mission_id}/informe.pdf"
            store_object(key, report, "application/pdf")
            if stored is None:
                stored = Informe(id_mision=mission_id, clave_objeto_s3=key)
            stored.clave_objeto_s3 = key
            stored.fecha_generacion = datetime.now(timezone.utc)
            stored.total_hallazgos = sum(item.estado_revision != "rejected" for item in detections)
            session.add(stored)
            session.commit()
        except (AnalysisStorageError, SQLAlchemyError) as error:
            session.rollback()
            raise HTTPException(503, detail="No se pudo guardar el informe.") from error
    return Response(
        content=report,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="informe-{mission.id_mision[:8]}.pdf"'},
    )
