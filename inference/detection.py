"""Prueba local de detección YOLO; no modifica el backend ni la base de datos."""

import argparse
import hashlib
import json
from functools import lru_cache
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
WEIGHTS = BASE_DIR / "models" / "weights_det.pt"


@lru_cache(maxsize=1)
def load_model(weights: Path):
    from ultralytics import YOLO

    model = YOLO(str(weights))
    if model.task != "detect":
        raise ValueError("El checkpoint debe ser un modelo YOLO de deteccion.")
    return model


def file_digest(path: Path) -> bytes:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.digest()


@lru_cache(maxsize=1)
def load_rock_model(weights: Path):
    if not weights.is_file():
        raise FileNotFoundError(f"No se encontraron los pesos: {weights}")
    segmentation_weights = BASE_DIR / "models" / "weights_seg.pt"
    if segmentation_weights.is_file() and file_digest(weights) == file_digest(segmentation_weights):
        raise ValueError(
            "Los pesos de deteccion son identicos a weights_seg.pt. "
            "Reemplaza weights_det.pt por el checkpoint YOLO de rocas."
        )
    return load_model(weights)


def tile_bounds(width: int, height: int, rows: int, columns: int):
    """Grilla sin solapamiento; conserva los pixeles de los bordes."""
    if not 1 <= rows <= height or not 1 <= columns <= width:
        raise ValueError("La grilla debe ser positiva y no superar la imagen.")
    for row in range(rows):
        for column in range(columns):
            yield (column * width // columns, row * height // rows,
                   (column + 1) * width // columns, (row + 1) * height // rows)


def run(image_path: Path, weights: Path, output: Path, confidence: float,
        imgsz: int, device: str | None = None,
        rows: int = 2, columns: int = 3, max_det: int = 600,
        *, image=None) -> dict:
    if not image_path.is_file():
        raise FileNotFoundError(f"No se encontro la imagen: {image_path}")
    if not 0 <= confidence <= 1:
        raise ValueError("La confianza debe estar entre 0 y 1.")
    if imgsz <= 0:
        raise ValueError("imgsz debe ser positivo.")
    if max_det <= 0:
        raise ValueError("max_det debe ser positivo.")

    import cv2

    if image is None:
        image = cv2.imread(str(image_path))
    if image is None:
        raise ValueError(f"Imagen invalida: {image_path}")
    height, width = image.shape[:2]
    bounds = list(tile_bounds(width, height, rows, columns))
    if (width, height) != (3840, 2160) and (rows, columns) == (2, 3):
        print(f"Aviso: imagen {width}x{height}; los tiles no seran 1280x1080. "
              "Se usa el tamaño indicado antes del letterbox.")
    model = load_rock_model(weights)
    detections = []
    tiles = []
    overlay = image.copy()
    for tile_index, (left, top, right, bottom) in enumerate(bounds):
        tile = image[top:bottom, left:right].copy()
        prediction = model.predict(
            source=tile, conf=confidence, imgsz=imgsz, max_det=max_det,
            rect=False, augment=False, device=device, verbose=False,
        )[0]
        tiles.append({"index": tile_index, "bbox": [left, top, right, bottom]})
        if prediction.boxes is not None:
            for box in prediction.boxes:
                class_id = int(box.cls.item())
                x1, y1, x2, y2 = [float(value) for value in box.xyxy[0].tolist()]
                detections.append({
                    "class": str(prediction.names[class_id]),
                    "confidence": float(box.conf.item()),
                    "bbox": [x1 + left, y1 + top, x2 + left, y2 + top],
                    "tile_index": tile_index,
                })
        overlay[top:bottom, left:right] = prediction.plot()
        print(f"Tile {tile_index + 1}/{len(bounds)}: {right-left}x{bottom-top}")
    result = {
        "image": image_path.name,
        "width": width,
        "height": height,
        "weights": weights.name,
        "confidence_threshold": confidence,
        "imgsz": imgsz,
        "rows": rows,
        "columns": columns,
        "max_det_per_tile": max_det,
        "tiles": tiles,
        "bbox_format": "xyxy_pixels",
        "detections": detections,
    }
    output.mkdir(parents=True, exist_ok=True)
    overlay_path = output / f"{image_path.stem}_rocks.jpg"
    if not cv2.imwrite(str(overlay_path), overlay):
        raise OSError(f"No se pudo guardar: {overlay_path}")
    json_path = output / f"{image_path.stem}_rocks.json"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Detecciones: {len(detections)}")
    print(f"Imagen: {overlay_path}")
    print(f"JSON: {json_path}")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path, help="Imagen o tile de prueba")
    parser.add_argument("--weights", type=Path, default=WEIGHTS)
    parser.add_argument("--output", type=Path, default=BASE_DIR / "outputs")
    parser.add_argument("--conf", type=float, default=0.30)
    parser.add_argument("--imgsz", type=int, default=1280)
    parser.add_argument("--rows", type=int, default=2)
    parser.add_argument("--columns", type=int, default=3)
    parser.add_argument("--max-det", type=int, default=600)
    parser.add_argument("--device", help="cpu o indice GPU, por ejemplo 0")
    args = parser.parse_args()
    try:
        run(args.image, args.weights, args.output, args.conf, args.imgsz, args.device,
            args.rows, args.columns, args.max_det)
    except (ValueError, OSError, ImportError) as error:
        parser.exit(1, f"Error: {error}\n")


if __name__ == "__main__":
    main()
