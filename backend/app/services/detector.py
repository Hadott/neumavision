import json
import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from random import Random
from typing import Protocol

import base64
from io import BytesIO

import httpx
from PIL import Image

from app.config import settings

logger = logging.getLogger(__name__)


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
    def predict(self, image_path: Path, *, output_path: Path | None = None) -> list[DetectionResult]:
        try:
            headers = ({"Authorization": f"Bearer {settings.inference_token}"}
                       if settings.inference_token else {})
            form = {"include_road_width": "true"}
            if settings.default_gsd_cm_px:
                form["default_gsd_cm_px"] = str(settings.default_gsd_cm_px)
            with image_path.open("rb") as stream:
                response = httpx.post(
                    settings.inference_url.rstrip("/") + "/predict",
                    files={"file": (image_path.name, stream, "application/octet-stream")},
                    data=form, headers=headers, timeout=settings.inference_timeout,
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
                results.append(DetectionResult(ROCK_LABEL, confidence, x1 / width,
                                               y1 / height, (x2-x1) / width,
                                               (y2-y1) / height))
            # Rocas fuera de la pista: se muestran en revision como referencia, no son hallazgos.
            for item in payload.get("off_road_detections", []):
                if item["alarm"] is not False:
                    raise ValueError("Roca fuera de pista mal clasificada")
                x1, y1, x2, y2 = item["bbox"]
                confidence = float(item["confidence"])
                if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height
                        and 0 <= confidence <= 1):
                    raise ValueError("Deteccion invalida")
                results.append(DetectionResult(OFF_ROAD_LABEL, confidence, x1 / width,
                                               y1 / height, (x2-x1) / width,
                                               (y2-y1) / height))
            overlay = base64.b64decode(payload["overlay_jpeg"], validate=True)
            with Image.open(BytesIO(overlay)) as rendered:
                if rendered.size != (width, height) or rendered.format != "JPEG":
                    raise ValueError("Imagen procesada invalida")
                rendered.verify()
            (output_path or overlay_path(image_path)).write_bytes(overlay)
            if payload.get("road_width"):
                try:
                    width_result = payload["road_width"]
                    width_jpeg = base64.b64decode(width_result["overlay_jpeg"], validate=True)
                    with Image.open(BytesIO(width_jpeg)) as rendered:
                        if rendered.size != (width, height) or rendered.format != "JPEG":
                            raise ValueError("Imagen de ancho invalida")
                        rendered.verify()
                    summary = width_result["summary"]
                    if not isinstance(summary, dict):
                        raise ValueError("Resumen de ancho invalido")
                    jpg_path, json_path = width_paths(image_path)
                    jpg_path.write_bytes(width_jpeg)
                    json_path.write_text(json.dumps(summary, ensure_ascii=False), encoding="utf-8")
                except (ValueError, OSError, KeyError, TypeError):
                    logger.warning("No se pudo guardar el ancho de pista de %s", image_path.name, exc_info=True)
            elif payload.get("road_mask_png"):
                try:
                    save_remote_road_width(image_path,
                                           base64.b64decode(payload["road_mask_png"], validate=True),
                                           payload.get("segmentation"))
                except (ValueError, OSError):
                    # Sin ancho la imagen sigue siendo util: se informan las rocas igual.
                    logger.warning("No se pudo medir el ancho de pista de %s", image_path.name, exc_info=True)
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


def _device() -> str:
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
        if torch.backends.mps.is_available():
            return "mps"
    except Exception:
        pass
    return "cpu"


ROCK_LABEL = "Rocas"
OFF_ROAD_LABEL = "Rocas fuera de pista"


def width_paths(image_path: Path) -> tuple[Path, Path]:
    """Archivos que acompanan a cada imagen con el analisis de ancho de pista."""
    return Path(f"{image_path}.ancho.jpg"), Path(f"{image_path}.ancho.json")


def save_road_width(image_path: Path, bgr, mask, road_conf: float | None, road_class: int | None) -> None:
    """Mide el ancho de pista sobre una mascara limpia (0/1) y guarda junto a la imagen
    <imagen>.ancho.jpg y <imagen>.ancho.json. Lo usan los modos neumavision y remote."""
    import cv2

    from app.services import ancho_pista

    overlay, summary = ancho_pista.analizar_archivo(
        image_path, bgr, mask, settings.default_gsd_cm_px, road_conf, road_class,
    )
    jpg_path, json_path = width_paths(image_path)
    if not cv2.imwrite(str(jpg_path), overlay, [cv2.IMWRITE_JPEG_QUALITY, 85]):
        raise OSError("No se pudo guardar el analisis de ancho")
    json_path.write_text(json.dumps(summary, ensure_ascii=False), encoding="utf-8")


def save_remote_road_width(image_path: Path, mask_png: bytes, segmentation: dict | None) -> None:
    """Compatibilidad con versiones de Jade que solo devuelven la máscara PNG."""
    import cv2
    import numpy as np

    from app.services import ancho_pista

    bgr = cv2.imread(str(image_path))
    mask = cv2.imdecode(np.frombuffer(mask_png, np.uint8), cv2.IMREAD_GRAYSCALE)
    if bgr is None or mask is None or mask.shape != bgr.shape[:2]:
        raise ValueError("Mascara de camino invalida")
    clean = ancho_pista.limpiar((mask > 0).astype(np.uint8))
    seg = segmentation or {}
    conf = seg.get("confidence")
    clase = seg.get("class_id")
    save_road_width(image_path, bgr, clean,
                    float(conf) if conf is not None else None,
                    int(clase) if clase is not None else None)


class NeumaVisionDetector:
    """Pipeline completo de NeumaVision:

    1. Modelo de pista (RF-DETR Seg) -> mascara del camino.
    2. Modelo de rocas (YOLO26) con tiling, para conservar la escala del entrenamiento.
    3. Filtro espacial: solo se reportan rocas sobre la pista.
    4. Ancho de pista con semaforo; se guarda junto a la imagen (<imagen>.ancho.jpg / .json).
    """


    def __init__(self) -> None:
        os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
        for path in (settings.rock_model_path, settings.road_model_path):
            if not Path(path).exists():
                raise RuntimeError(f"Modelo no encontrado en {path}")
        try:
            from rfdetr import RFDETRSegMedium
            from ultralytics import YOLO
        except ImportError as error:
            raise RuntimeError("Instala ultralytics, rfdetr y scikit-image para DETECTOR_MODE=neumavision") from error
        self.device = _device()
        self.rock_model = YOLO(str(settings.rock_model_path))
        self.road_model = RFDETRSegMedium(pretrain_weights=str(settings.road_model_path))

    # ---- rocas ----
    def _rocks(self, rgb) -> list[tuple[float, float, float, float, float]]:
        import numpy as np

        h, w = rgb.shape[:2]
        cols = max(1, round(w / settings.tile_width))
        rows = max(1, round(h / settings.tile_height))
        tw, th = w / cols, h / rows
        tiles, offsets = [], []
        for r in range(rows):
            for c in range(cols):
                x0, y0 = int(round(c * tw)), int(round(r * th))
                x1, y1 = int(round((c + 1) * tw)), int(round((r + 1) * th))
                tiles.append(np.ascontiguousarray(rgb[y0:y1, x0:x1, ::-1]))  # BGR para ultralytics
                offsets.append((x0, y0))
        boxes = []
        results = self.rock_model.predict(
            tiles, imgsz=settings.tile_width, conf=settings.rock_confidence, iou=0.6,
            max_det=600, device=self.device, verbose=False,
        )
        for (ox, oy), result in zip(offsets, results):
            for xyxy, conf in zip(result.boxes.xyxy.tolist(), result.boxes.conf.tolist()):
                x1, y1, x2, y2 = xyxy
                boxes.append((x1 + ox, y1 + oy, x2 + ox, y2 + oy, float(conf)))
        return boxes

    # ---- pista ----
    def _road_mask(self, rgb):
        """Mascara limpia de la pista y la confianza del modelo de segmentacion."""
        from app.services import ancho_pista

        mask, conf, clase = ancho_pista.mascara_pista_conf(self.road_model, rgb, settings.road_confidence)
        return ancho_pista.limpiar(mask), conf, clase

    def predict(self, image_path: Path) -> list[DetectionResult]:
        import cv2
        import numpy as np

        from app.services import ancho_pista

        bgr = cv2.imread(str(image_path))
        if bgr is None:
            return []
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        h, w = rgb.shape[:2]

        mask, road_conf, road_class = self._road_mask(rgb)
        has_road = bool(mask.any())

        # ancho de pista
        save_road_width(image_path, bgr, mask, road_conf, road_class)

        # rocas filtradas por la pista (margen para bermas/bordes)
        if has_road:
            k = max(3, int(min(h, w) * settings.road_margin)) | 1
            road = cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
        # Rocas sobre la pista -> "Rocas"; fuera de la pista -> "Rocas fuera de pista"
        # (se muestran en revision con otro color, pero no cuentan como hallazgo del informe).
        results: list[DetectionResult] = []
        for x1, y1, x2, y2, conf in self._rocks(rgb):
            cx, cy = int((x1 + x2) / 2), int((y1 + y2) / 2)
            inside = (not has_road) or bool(road[min(cy, h - 1), min(cx, w - 1)])
            results.append(
                DetectionResult(
                    label=ROCK_LABEL if inside else OFF_ROAD_LABEL,
                    confidence=round(conf, 4),
                    x=x1 / w, y=y1 / h, width=(x2 - x1) / w, height=(y2 - y1) / h,
                )
            )
        return results


@lru_cache(maxsize=1)
def _neumavision_detector() -> NeumaVisionDetector:
    # Los modelos se cargan una sola vez por proceso.
    return NeumaVisionDetector()


def get_detector() -> Detector:
    mode = settings.detector_mode.lower()
    if mode == "remote":
        return RemoteDetector()
    if mode == "neumavision":
        return _neumavision_detector()
    if mode == "yolo":
        return YoloDetector(settings.yolo_model_path)
    if settings.detector_mode.lower() == "mock":
        return MockDetector()
    raise DetectorError("DETECTOR_MODE debe ser remote, neumavision, yolo o mock")
