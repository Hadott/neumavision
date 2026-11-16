"""Servicio privado de inferencia; no accede a RDS ni a S3."""

import base64
import logging
import os
import secrets
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock

import cv2
from fastapi import FastAPI, File, Header, HTTPException, UploadFile

from pipeline import run

app = FastAPI(title="NeumaVision inference")
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
                "overlay_jpeg": base64.b64encode((root / "image_alarms.jpg").read_bytes()).decode("ascii"),
            }
        except (OSError, ValueError, RuntimeError) as error:
            logger.exception("Fallo la inferencia")
            raise HTTPException(503, "No se pudo completar la inferencia") from error
