"""Servicio privado de inferencia; no accede a RDS ni a S3."""

import base64
import logging
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock

import cv2
from fastapi import FastAPI, File, Header, HTTPException, UploadFile

from detection import WEIGHTS as ROCK_WEIGHTS, load_rock_model
from pipeline import run
from segmentation import WEIGHTS as ROAD_WEIGHTS, load_model as load_road_model

@asynccontextmanager
async def lifespan(app: FastAPI):
    if os.environ.get("INFERENCE_PRELOAD") == "1":
        if not os.environ.get("INFERENCE_TOKEN"):
            raise RuntimeError("Configura INFERENCE_TOKEN para ejecutar Jade.")
        load_road_model(ROAD_WEIGHTS)
        load_rock_model(ROCK_WEIGHTS)
    yield


app = FastAPI(title="NeumaVision inference", lifespan=lifespan)
model_lock = Lock()
logger = logging.getLogger(__name__)
MAX_UPLOAD = 30 * 1024 * 1024


@app.get("/health")
def health():
    return {"status": "ok", "pipeline": "road_rocks"}


@app.post("/predict")
def predict(file: UploadFile = File(...), authorization: str | None = Header(default=None)):
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
        if cv2.imread(str(source)) is None:
            raise HTTPException(422, "Imagen invalida")
        try:
            with model_lock:
                result = run(source, root, draw_candidates=False)
            if result["cross_status"] != "evaluated":
                raise HTTPException(422, "No se obtuvo mascara del camino; cruce no evaluado")
            return {
                "width": result["width"], "height": result["height"],
                "segmentation": result["segmentation"],
                "detections": [item for item in result["detections"] if item["alarm"] is True],
                # Rocas que no tocan la mascara: el backend las muestra como referencia.
                "off_road_detections": [item for item in result["detections"] if item["alarm"] is False],
                "overlay_jpeg": base64.b64encode((root / "image_alarms.jpg").read_bytes()).decode("ascii"),
                # Mascara del camino (PNG 0/255): el backend mide con ella el ancho de pista.
                "road_mask_png": (base64.b64encode(mask_file.read_bytes()).decode("ascii")
                                  if (mask_file := root / "image_road_mask.png").is_file() else None),
            }
        except (OSError, ValueError, RuntimeError) as error:
            logger.exception("Fallo la inferencia")
            raise HTTPException(503, "No se pudo completar la inferencia") from error
