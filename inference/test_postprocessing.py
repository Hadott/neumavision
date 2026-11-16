import unittest
from types import SimpleNamespace

import numpy as np

from postprocessing import cross_detections
from segmentation import select_road_mask


class CrossingTests(unittest.TestCase):
    def test_overlap_outside_partial_and_clipped_boxes(self):
        mask = np.zeros((10, 10), dtype=np.uint8)
        mask[3:7, 3:7] = 255
        boxes = [[4, 4, 6, 6], [0, 0, 2, 2], [2, 2, 4, 4],
                 [-5, -5, 4, 4], [-5, -5, -1, -1], [7, 3, 9, 7]]
        source = [{"bbox": box} for box in boxes]
        results = cross_detections(source, mask, True)
        self.assertEqual([item["alarm"] for item in results],
                         [True, False, True, True, False, False])
        self.assertEqual([item["road_overlap_pixels"] for item in results],
                         [4, 0, 1, 1, 0, 0])
        self.assertNotIn("alarm", source[0])

    def test_no_mask_is_unknown_and_no_detections_is_empty(self):
        mask = np.zeros((10, 10), dtype=np.uint8)
        result = cross_detections([{"bbox": [1, 1, 2, 2]}], mask, False)
        self.assertIsNone(result[0]["alarm"])
        self.assertIsNone(result[0]["road_overlap_pixels"])
        self.assertEqual(cross_detections([], mask, True), [])

    def test_selects_highest_confidence_even_below_point_four(self):
        detections = SimpleNamespace(
            mask=np.array([[[1, 0], [0, 0]], [[0, 0], [0, 1]]], dtype=bool),
            confidence=np.array([0.1, 0.3]), class_id=np.array([1, 2]))
        mask, selected = select_road_mask(detections, 4, 4)
        self.assertEqual(selected, {"confidence": 0.3, "class_id": 2})
        self.assertEqual(int(mask[:2, :2].sum()), 0)
        self.assertTrue(np.all(mask[2:, 2:] == 255))

    def test_missing_masks(self):
        mask, selected = select_road_mask(SimpleNamespace(mask=None), 4, 4)
        self.assertIsNone(selected)
        self.assertEqual(int(mask.sum()), 0)


if __name__ == "__main__":
    unittest.main()
