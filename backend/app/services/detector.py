from dataclasses import dataclass
from pathlib import Path
from random import Random
from typing import Protocol

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


class MockDetector:
    """Deterministic demo detector. Replace this adapter without changing the API."""

    labels = ("Bache", "Piedra", "Desprendimiento de roca")

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
    if settings.detector_mode.lower() == "yolo":
        return YoloDetector(settings.yolo_model_path)
    return MockDetector()
