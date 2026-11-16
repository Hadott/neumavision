
import argparse
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
import torch
from rfdetr import RFDETRSegMedium

BASE_DIR = Path(__file__).resolve().parent
WEIGHTS = BASE_DIR / "models" / "weights_seg.pt"
INPUT_DIR = BASE_DIR / "test_images"
OUTPUT_DIR = BASE_DIR / "outputs"

# Conservar todos los candidatos para seleccionar el de mayor confianza.
CONFIDENCE = 0.0


def select_road_mask(detections, height: int, width: int):
    road_mask = np.zeros((height, width), dtype=np.uint8)
    if detections.mask is None or len(detections.mask) == 0:
        return road_mask, None
    best_index = int(np.argmax(detections.confidence))
    mask = detections.mask[best_index]
    if mask.shape != (height, width):
        mask = cv2.resize(mask.astype(np.uint8), (width, height),
                          interpolation=cv2.INTER_NEAREST)
    road_mask = mask.astype(np.uint8) * 255
    return road_mask, {
        "confidence": float(detections.confidence[best_index]),
        "class_id": int(detections.class_id[best_index]),
    }


@lru_cache(maxsize=1)
def load_model(weights: Path):
    if not weights.is_file():
        raise FileNotFoundError(f"No se encontraron los pesos: {weights}")
    print("Cargando RF-DETR...")
    return RFDETRSegMedium(pretrain_weights=str(weights))


def predict_road(image, weights: Path = WEIGHTS):
    model = load_model(weights)
    print("Ejecutando segmentacion...")
    detections = model.predict(cv2.cvtColor(image, cv2.COLOR_BGR2RGB),
                               threshold=CONFIDENCE)
    return select_road_mask(detections, *image.shape[:2])


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
