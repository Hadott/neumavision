
import argparse
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

BASE_DIR = Path(__file__).resolve().parent
WEIGHTS = BASE_DIR / "models" / "weights_seg.pt"
INPUT_DIR = BASE_DIR / "test_images"
OUTPUT_DIR = BASE_DIR / "outputs"

# IDs usados por el visor, independientes del orden del dataset YOLO.
ROAD_CLASSES = {
    "camino": 1,
    "camino en buen estado": 1,
    "camino rocoso": 2,
    "camino con material pedregoso": 2,
}


def road_class_ids(names: dict[int, str]) -> dict[int, int]:
    classes = {}
    for class_id, name in names.items():
        normalized = " ".join(name.lower().replace("_", " ").replace("-", " ").split())
        if normalized in ROAD_CLASSES:
            classes[class_id] = ROAD_CLASSES[normalized]
    if not classes:
        raise ValueError(f"El segmentador no contiene clases de camino reconocidas: {names}")
    return classes


@lru_cache(maxsize=1)
def load_model(weights: Path):
    if not weights.is_file():
        raise FileNotFoundError(f"No se encontraron los pesos: {weights}")

    from ultralytics import YOLO

    model = YOLO(str(weights))
    if model.task != "segment":
        raise ValueError(f"Se requiere un checkpoint YOLO de segmentación: {weights}")
    road_class_ids(model.names)
    return model


def predict_road(image, weights: Path = WEIGHTS):
    model = load_model(weights)
    classes = road_class_ids(model.names)
    result = model.predict(
        image, conf=0.0, classes=list(classes), max_det=1,
        retina_masks=True, verbose=False,
    )[0]
    if result.masks is None or len(result.masks) == 0:
        return np.zeros(image.shape[:2], dtype=np.uint8), None

    result = result.cpu().numpy()
    road_mask = result.masks.data[0].astype(np.uint8) * 255
    return road_mask, {
        "confidence": float(result.boxes.conf[0]),
        "class_id": classes[int(result.boxes.cls[0])],
    }


def main(image_path: Path | None = None):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    images = [image_path] if image_path is not None else [
        p for p in INPUT_DIR.iterdir()
        if p.suffix.lower() in {".jpg", ".jpeg", ".png"}
    ]

    if not WEIGHTS.is_file():
        raise FileNotFoundError(f"No se encontraron los pesos: {WEIGHTS}")

    if not images:
        raise FileNotFoundError("Coloca una imagen en test_images/")

    image_path = images[0]
    image = cv2.imread(str(image_path))

    if image is None:
        raise RuntimeError("No se pudo leer la imagen")

    height, width = image.shape[:2]

    import torch

    print("GPU:", torch.cuda.get_device_name(0) if torch.cuda.is_available() else "No disponible")
    print("Imagen:", image_path.name)
    print("Resolucion:", width, "x", height)

    road_mask, selected = predict_road(image)

    if selected is not None:
        print("Confianza de la mascara seleccionada:",
              f"{selected['confidence']:.4f}")
        print("Clase:", selected["class_id"])
        print("Cobertura de la mascara:",
              f"{np.count_nonzero(road_mask) / road_mask.size:.1%}")
    else:
        print("No se detectaron mascaras con el umbral configurado.")

    overlay = image.copy()
    overlay[road_mask > 0] = (0, 180, 0)

    result = cv2.addWeighted(image, 0.65, overlay, 0.35, 0)

    cv2.imwrite(str(OUTPUT_DIR / "road_mask.png"), road_mask)
    cv2.imwrite(str(OUTPUT_DIR / "road_overlay.jpg"), result)

    print("Mascara seleccionada:", selected is not None)
    print("Resultados guardados en outputs/")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("image", nargs="?", type=Path)
    main(parser.parse_args().image)
