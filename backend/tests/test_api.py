from fastapi.testclient import TestClient

from app.main import app


def test_demo_detection_and_report() -> None:
    with TestClient(app) as client:
        health = client.get("/api/v1/health")
        assert health.status_code == 200
        assert health.json()["detector"] == "mock"

        demo = client.post("/api/v1/missions/demo")
        assert demo.status_code == 201
        mission = demo.json()
        assert len(mission["images"]) == 4

        detected = client.post(f"/api/v1/missions/{mission['id']}/detect")
        assert detected.status_code == 200
        payload = detected.json()
        assert payload["status"] == "review"
        assert sum(len(image["detections"]) for image in payload["images"]) >= 4

        report = client.get(f"/api/v1/missions/{mission['id']}/report")
        assert report.status_code == 200
        assert report.headers["content-type"] == "application/pdf"
        assert report.content.startswith(b"%PDF")
