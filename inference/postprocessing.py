"""Cruce de cajas en coordenadas originales con la mascara del camino."""

from math import ceil, floor

import numpy as np


def cross_detections(detections: list[dict], mask: np.ndarray,
                     mask_available: bool) -> list[dict]:
    if mask.ndim != 2:
        raise ValueError("La mascara debe tener dos dimensiones.")
    height, width = mask.shape
    results = []
    for detection in detections:
        x1, y1, x2, y2 = detection["bbox"]
        left, top = max(0, floor(x1)), max(0, floor(y1))
        right, bottom = min(width, ceil(x2)), min(height, ceil(y2))
        overlap = (int(np.count_nonzero(mask[top:bottom, left:right]))
                   if right > left and bottom > top and mask_available else 0)
        results.append({**detection,
                        "road_overlap_pixels": overlap if mask_available else None,
                        "alarm": overlap > 0 if mask_available else None})
    return results
