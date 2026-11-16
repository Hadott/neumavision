from dataclasses import dataclass
from pathlib import Path
from random import Random
from typing import Protocol

import base64
from io import BytesIO

import httpx
from PIL import Image

from app.config import settings


@dataclass(frozen=True)
class DetectionResult:
    label: str
    confidence: float
    x: float
    y: float
    width: float
    height: float


class Detector(Protocol):
    def predict(self, image_path: Path) -> list[DetectionResult]: ...


class DetectorError(RuntimeError):
    """El fallo de inferencia no equivale a cero hallazgos."""


def overlay_path(image_path: Path) -> Path:
    return image_path.with_suffix(image_path.suffix + ".vision.jpg")


class RemoteDetector:
    def predict(self, image_path: Path) -> list[DetectionResult]:
        try:
            headers = ({"Authorization": f"Bearer {settings.inference_token}"}
                       if settings.inference_token else {})
            with image_path.open("rb") as stream:
                response = httpx.post(
                    settings.inference_url.rstrip("/") + "/predict",
                    files={"file": (image_path.name, stream, "application/octet-stream")},
                    headers=headers, timeout=settings.inference_timeout,
                )
            response.raise_for_status()
            payload = response.json()
            with Image.open(image_path) as original:
                width, height = original.size
            if payload["width"] != width or payload["height"] != height:
                raise ValueError("Dimensiones de inferencia inconsistentes")
            results = []
            for item in payload["detections"]:
                if item["alarm"] is not True:
                    raise ValueError("El servicio devolvio candidatos fuera del camino")
                x1, y1, x2, y2 = item["bbox"]
                confidence = float(item["confidence"])
                if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height
                        and 0 <= confidence <= 1):
                    raise ValueError("Deteccion invalida")
                results.append(DetectionResult("Rocas", confidence, x1 / width,
                                               y1 / height, (x2-x1) / width,
                                               (y2-y1) / height))
            overlay = base64.b64decode(payload["overlay_jpeg"], validate=True)
            with Image.open(BytesIO(overlay)) as rendered:
                if rendered.size != (width, height) or rendered.format != "JPEG":
                    raise ValueError("Imagen procesada invalida")
                rendered.verify()
            overlay_path(image_path).write_bytes(overlay)
            return results
        except (httpx.HTTPError, OSError, ValueError, KeyError, TypeError) as error:
            raise DetectorError("No se pudo analizar la imagen con el servicio de inferencia") from error


class MockDetector:
    """Deterministic demo detector. Replace this adapter without changing the API."""

    labels = ("Rocas", "Carpeta Buen Estado", "Material Pedregoso")

    def predict(self, image_path: Path) -> list[DetectionResult]:
        random = Random(image_path.name)
        total = random.randint(1, 3)
        results: list[DetectionResult] = []
        for _ in range(total):
            width = random.uniform(0.12, 0.28)
            height = random.uniform(0.10, 0.23)
            results.append(
                DetectionResult(
                    label=random.choice(self.labels),
                    confidence=round(random.uniform(0.68, 0.94), 3),
                    x=round(random.uniform(0.05, 0.95 - width), 3),
                    y=round(random.uniform(0.12, 0.92 - height), 3),
                    width=round(width, 3),
                    height=round(height, 3),
                )
            )
        return results


class YoloDetector:
    """Integration point for an Ultralytics/Roboflow model."""

    def __init__(self, model_path: Path) -> None:
        if not model_path.exists():
            raise RuntimeError(f"YOLO model not found at {model_path}")
        try:
            from ultralytics import YOLO
        except ImportError as error:
            raise RuntimeError("Install ultralytics to use DETECTOR_MODE=yolo") from error
        self.model = YOLO(str(model_path))

    def predict(self, image_path: Path) -> list[DetectionResult]:
        prediction = self.model.predict(str(image_path), verbose=False)[0]
        names = prediction.names
        results: list[DetectionResult] = []
        image_height, image_width = prediction.orig_shape
        for box in prediction.boxes:
            x1, y1, x2, y2 = [float(value) for value in box.xyxy[0].tolist()]
            results.append(
                DetectionResult(
                    label=str(names[int(box.cls[0])]),
                    confidence=float(box.conf[0]),
                    x=x1 / image_width,
                    y=y1 / image_height,
                    width=(x2 - x1) / image_width,
                    height=(y2 - y1) / image_height,
                )
            )
        return results


def get_detector() -> Detector:
    if settings.detector_mode.lower() == "remote":
        return RemoteDetector()
    if settings.detector_mode.lower() == "yolo":
        return YoloDetector(settings.yolo_model_path)
    if settings.detector_mode.lower() == "mock":
        return MockDetector()
    raise DetectorError("DETECTOR_MODE debe ser remote, yolo o mock")
