"""Servicio privado de inferencia; no accede a RDS ni a S3."""

import base64
import logging
import os
import secrets
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock
from time import perf_counter

import cv2
from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile

from detection import WEIGHTS as ROCK_WEIGHTS, load_rock_model
from pipeline import run
from segmentation import WEIGHTS as ROAD_WEIGHTS, load_model as load_road_model

# El módulo de medición también se usa en el modo local del backend.
sys.path.append(str(Path(__file__).resolve().parents[1] / "backend"))
from app.services.ancho_pista import analizar_archivo, limpiar


@asynccontextmanager
async def lifespan(app: FastAPI):
    if os.environ.get("INFERENCE_PRELOAD") == "1":
        if not os.environ.get("INFERENCE_TOKEN"):
            raise RuntimeError("Configura INFERENCE_TOKEN para ejecutar el servicio de inferencia.")
        load_road_model(ROAD_WEIGHTS)
        load_rock_model(ROCK_WEIGHTS)
    yield


app = FastAPI(title="NeumaVision inference", lifespan=lifespan)
model_lock = Lock()
logger = logging.getLogger("uvicorn.error")
MAX_UPLOAD = 30 * 1024 * 1024


@app.get("/health")
def health():
    return {"status": "ok", "pipeline": "road_rocks"}


@app.post("/predict")
def predict(
    file: UploadFile = File(...),
    authorization: str | None = Header(default=None),
    include_road_width: bool = Form(default=False),
    default_gsd_cm_px: float | None = Form(default=None, gt=0, allow_inf_nan=False),
):
    token = os.environ.get("INFERENCE_TOKEN")
    if token and not secrets.compare_digest(authorization or "", f"Bearer {token}"):
        raise HTTPException(401, "Credenciales de inferencia invalidas")
    content = file.file.read(MAX_UPLOAD + 1)
    if len(content) > MAX_UPLOAD:
        raise HTTPException(413, "Imagen demasiado grande (maximo 30 MiB)")
    with TemporaryDirectory(prefix="neumavision-") as directory:
        root = Path(directory)
        source = root / "image.jpg"
        source.write_bytes(content)
        bgr = cv2.imread(str(source))
        if bgr is None:
            raise HTTPException(422, "Imagen invalida")
        height, width = bgr.shape[:2]
        try:
            queued_at = perf_counter()
            with model_lock:
                inference_started = perf_counter()
                result = run(source, root, draw_candidates=False)
                inference_seconds = perf_counter() - inference_started
            logger.info(
                "Imagen %r (%dx%d): inferencia %.2f s, espera de modelos %.2f s",
                file.filename, width, height, inference_seconds, inference_started - queued_at,
            )
            if result["cross_status"] != "evaluated":
                raise HTTPException(422, "No se obtuvo mascara del camino; cruce no evaluado")
            response = {
                "width": result["width"], "height": result["height"],
                "segmentation": result["segmentation"],
                "detections": [item for item in result["detections"] if item["alarm"] is True],
                # Rocas que no tocan la mascara: el backend las muestra como referencia.
                "off_road_detections": [item for item in result["detections"] if item["alarm"] is False],
                "overlay_jpeg": base64.b64encode((root / "image_alarms.jpg").read_bytes()).decode("ascii"),
            }
            mask_file = root / "image_road_mask.png"
            if include_road_width:
                started = perf_counter()
                try:
                    mask = cv2.imread(str(mask_file), cv2.IMREAD_GRAYSCALE)
                    if mask is None or mask.shape != bgr.shape[:2]:
                        raise ValueError("Máscara de camino inválida")
                    segmentation = result["segmentation"]
                    overlay, summary = analizar_archivo(
                        source, bgr, limpiar((mask > 0).astype("uint8")), default_gsd_cm_px,
                        segmentation["confidence"], segmentation["class_id"], media_resolucion=True,
                    )
                    ok, jpeg = cv2.imencode(".jpg", overlay, [cv2.IMWRITE_JPEG_QUALITY, 85])
                    if not ok:
                        raise OSError("No se pudo codificar el análisis de ancho")
                    response["road_width"] = {
                        "summary": summary,
                        "overlay_jpeg": base64.b64encode(jpeg.tobytes()).decode("ascii"),
                    }
                    logger.info("Imagen %r: ancho de pista calculado en %.2f s",
                                file.filename, perf_counter() - started)
                except (OSError, ValueError, RuntimeError, cv2.error):
                    logger.warning("Imagen %r: falló el cálculo de ancho de pista tras %.2f s",
                                   file.filename, perf_counter() - started, exc_info=True)
            else:
                response["road_mask_png"] = (
                    base64.b64encode(mask_file.read_bytes()).decode("ascii") if mask_file.is_file() else None
                )
            return response
        except (OSError, ValueError, RuntimeError) as error:
            logger.exception("Fallo la inferencia")
            raise HTTPException(503, "No se pudo completar la inferencia") from error
