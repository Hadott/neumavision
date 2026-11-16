import base64
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
from fastapi.testclient import TestClient

import api


class InferenceApiTests(unittest.TestCase):
    def test_valid_invalid_missing_mask_and_failure(self):
        client = TestClient(api.app)
        ok, encoded = cv2.imencode(".jpg", np.zeros((20, 30, 3), dtype=np.uint8))
        self.assertTrue(ok)
        image = encoded.tobytes()
        def fake_run(source, output, **kwargs):
            (output / "image_alarms.jpg").write_bytes(image)
            return {"width": 30, "height": 20, "segmentation": {"class_id": 1},
                    "cross_status": "evaluated", "detections": [
                        {"alarm": True, "bbox": [1, 1, 3, 3], "confidence": 0.5},
                        {"alarm": False, "bbox": [5, 5, 7, 7], "confidence": 0.5}]}
        with patch.dict("os.environ", {"INFERENCE_TOKEN": "test-token"}):
            self.assertEqual(client.post("/predict", files={"file": ("a.jpg", image)}).status_code, 401)
            headers = {"Authorization": "Bearer test-token"}
            self.assertEqual(client.post("/predict", headers=headers, files={"file": ("a.jpg", b"invalid")}).status_code, 422)
            with patch.object(api, "run", side_effect=fake_run):
                response = client.post("/predict", headers=headers, files={"file": ("a.jpg", image)})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(len(response.json()["detections"]), 1)
                self.assertEqual(base64.b64decode(response.json()["overlay_jpeg"]), image)
            with patch.object(api, "run", return_value={"cross_status": "no_road_mask"}):
                self.assertEqual(client.post("/predict", headers=headers, files={"file": ("a.jpg", image)}).status_code, 422)
            with patch.object(api, "run", side_effect=RuntimeError("model failed")):
                self.assertEqual(client.post("/predict", headers=headers, files={"file": ("a.jpg", image)}).status_code, 503)


if __name__ == "__main__":
    unittest.main()
