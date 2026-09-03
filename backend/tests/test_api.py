from fastapi.testclient import TestClient
from sqlmodel import Session

from app.config import settings
from app.database import engine
from app.main import app
from app.models import Mision


def test_demo_detection_and_report() -> None:
    with TestClient(app) as client:
        mission_id: str | None = None
        try:
            health = client.get("/api/v1/health")
            assert health.status_code == 200
            assert health.json()["detector"] == "mock"
            assert health.json()["database"] == "postgresql"

            demo = client.post("/api/v1/missions/demo")
            assert demo.status_code == 201
            mission = demo.json()
            mission_id = mission["id"]
            assert len(mission["images"]) == 4

            with Session(engine) as session:
                stored_mission = session.get(Mision, mission_id)
                assert stored_mission is not None
                assert stored_mission.id_faena == settings.development_faena_id

            detected = client.post(f"/api/v1/missions/{mission_id}/detect")
            assert detected.status_code == 200
            payload = detected.json()
            assert payload["status"] == "review"
            assert sum(len(image["detections"]) for image in payload["images"]) >= 4

            report = client.get(f"/api/v1/missions/{mission_id}/report")
            assert report.status_code == 200
            assert report.headers["content-type"] == "application/pdf"
            assert report.content.startswith(b"%PDF")
        finally:
            if mission_id is not None:
                client.delete(f"/api/v1/missions/{mission_id}")
