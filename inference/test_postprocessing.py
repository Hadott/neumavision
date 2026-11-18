import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np

from postprocessing import cross_detections
from segmentation import predict_road


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

    @patch("segmentation.load_model")
    def test_yolo_mask_preserves_road_class_and_confidence(self, load_model):
        image = np.zeros((4, 6, 3), dtype=np.uint8)
        model = load_model.return_value
        model.names = {0: "Camino Rocoso", 1: "Camino", 2: "Otra clase"}
        pixels = np.zeros((1, 4, 6), dtype=np.uint8)
        pixels[0, 2:, 3:] = 1
        result = Mock(masks=[object()])
        result.cpu.return_value.numpy.return_value = SimpleNamespace(
            masks=SimpleNamespace(data=pixels),
            boxes=SimpleNamespace(conf=[0.3], cls=[0]),
        )
        model.predict.return_value = [result]

        mask, selected = predict_road(image)

        self.assertEqual(selected, {"confidence": 0.3, "class_id": 2})
        np.testing.assert_array_equal(mask, pixels[0] * 255)
        self.assertIs(model.predict.call_args.args[0], image)
        options = model.predict.call_args.kwargs
        self.assertEqual(options["classes"], [0, 1])
        self.assertEqual(options["max_det"], 1)
        self.assertTrue(options["retina_masks"])

    @patch("segmentation.load_model")
    def test_missing_masks(self, load_model):
        model = load_model.return_value
        model.names = {0: "Camino"}
        model.predict.return_value = [SimpleNamespace(masks=None)]

        mask, selected = predict_road(np.zeros((4, 6, 3), dtype=np.uint8))

        self.assertIsNone(selected)
        np.testing.assert_array_equal(mask, np.zeros((4, 6), dtype=np.uint8))


if __name__ == "__main__":
    unittest.main()
