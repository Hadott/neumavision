"""Inferencia local de camino y rocas con alarma por interseccion."""

import argparse
import json
from pathlib import Path

import cv2

from detection import BASE_DIR, WEIGHTS, run as detect_rocks
from postprocessing import cross_detections
from segmentation import predict_road

MAX_INFERENCE_SIDE = 3840

ROAD_LABELS = {
    1: "Camino en buen estado",
    2: "Camino con material pedregoso",
}


def run(image_path: Path, output: Path, confidence: float = 0.30,
        draw_candidates: bool = True) -> dict:
    image = cv2.imread(str(image_path))
    if image is None:
        raise ValueError(f"No se pudo leer la imagen: {image_path}")
    height, width = image.shape[:2]
    inference_image = image
    if max(width, height) > MAX_INFERENCE_SIDE:
        scale = MAX_INFERENCE_SIDE / max(width, height)
        size = (max(1, round(width * scale)), max(1, round(height * scale)))
        inference_image = cv2.resize(image, size, interpolation=cv2.INTER_AREA)

    mask, selected = predict_road(inference_image)
    result = detect_rocks(image_path, WEIGHTS, output, confidence, 1280,
                          image=inference_image)
    if inference_image is not image:
        scale_x = width / result["width"]
        scale_y = height / result["height"]
        for detection in result["detections"]:
            x1, y1, x2, y2 = detection["bbox"]
            detection["bbox"] = [x1 * scale_x, y1 * scale_y, x2 * scale_x, y2 * scale_y]
        for tile in result["tiles"]:
            left, top, right, bottom = tile["bbox"]
            tile["bbox"] = [round(left * scale_x), round(top * scale_y),
                            round(right * scale_x), round(bottom * scale_y)]
        result.update(width=width, height=height)
        mask = cv2.resize(mask, (width, height), interpolation=cv2.INTER_NEAREST)
    result["detections"] = cross_detections(result["detections"], mask, selected is not None)
    alarm_count = sum(item["alarm"] is True for item in result["detections"])
    result.update({
        "segmentation": selected,
        "cross_status": "evaluated" if selected is not None else "no_road_mask",
        "alarm": alarm_count > 0 if selected is not None else None,
        "alarm_count": alarm_count if selected is not None else None,
        "alarm_rule": "bbox_intersects_road_mask",
    })
    tint = image.copy()
    road_color = (0, 140, 255) if selected is not None and selected["class_id"] == 2 else (0, 180, 0)
    tint[mask > 0] = road_color
    overlay = cv2.addWeighted(image, 0.65, tint, 0.35, 0)
    for index, detection in enumerate(result["detections"] if draw_candidates else [], start=1):
        x1, y1, x2, y2 = [round(value) for value in detection["bbox"]]
        color = (0, 0, 255) if detection["alarm"] else (0, 200, 255)
        cv2.rectangle(overlay, (x1, y1), (x2, y2), color, 2)
        cv2.putText(overlay, f"{index}: {detection['confidence']:.2f}",
                    (x1, max(30 if detection["alarm"] else 15, y1 - 5)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1.0 if detection["alarm"] else 0.5,
                    color, 3 if detection["alarm"] else 1)
    message = (f"ALARMA: {alarm_count} rocas sobre camino" if alarm_count else
               "Sin rocas sobre camino" if selected is not None else
               "SIN MASCARA: cruce no evaluado")
    cv2.putText(overlay, message, (20, 45), cv2.FONT_HERSHEY_SIMPLEX,
                1, (0, 0, 255) if alarm_count else (0, 200, 255), 2)
    if selected is not None and cv2.countNonZero(mask):
        road_label = ROAD_LABELS.get(selected['class_id'], 'Clase desconocida')
        # Anclar en el interior de la mascara, lejos de sus bordes.
        distance = cv2.distanceTransform(mask, cv2.DIST_L2, 5)
        _, _, _, (center_x, center_y) = cv2.minMaxLoc(distance)
        (text_width, text_height), baseline = cv2.getTextSize(
            road_label, cv2.FONT_HERSHEY_SIMPLEX, 1.8, 3)
        height, width = overlay.shape[:2]
        x = max(6, min(center_x - text_width // 2, width - text_width - 6))
        y = max(text_height + 6, min(center_y + text_height // 2,
                                     height - baseline - 6))
        cv2.rectangle(overlay, (x - 5, y - text_height - 5),
                      (x + text_width + 5, y + baseline + 5), (30, 30, 30), -1)
        cv2.putText(overlay, road_label, (x, y), cv2.FONT_HERSHEY_SIMPLEX,
                    1.8, (255, 255, 255), 3)
    for filename, pixels in [(f"{image_path.stem}_road_mask.png", mask),
                             (f"{image_path.stem}_alarms.jpg", overlay)]:
        if not cv2.imwrite(str(output / filename), pixels):
            raise OSError(f"No se pudo guardar {filename}")
    json_path = output / f"{image_path.stem}_alarms.json"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(message)
    print(f"Resultados: {json_path}")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--output", type=Path, default=BASE_DIR / "outputs")
    parser.add_argument("--conf", type=float, default=0.30)
    args = parser.parse_args()
    try:
        run(args.image, args.output, args.conf)
    except (OSError, ValueError, ImportError) as error:
        parser.exit(1, f"Error: {error}\n")
