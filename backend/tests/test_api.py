from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from app.config import settings
from app.database import get_session
from app.main import app
from app.models import Faena, Mision, Usuario
from app.services.auth import create_token


def test_demo_detection_and_report(tmp_path, monkeypatch) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'demo.db'}")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(settings, "analysis_s3_bucket", "")
    monkeypatch.setattr(settings, "upload_dir", tmp_path / "uploads")

    def get_test_session():
        with Session(engine) as session:
            yield session

    monkeypatch.setitem(app.dependency_overrides, get_session, get_test_session)
    with Session(engine) as session:
        session.add(Faena(id_faena="demo-faena", nombre="Faena de demostración"))
        session.add(Usuario(id_usuario="demo-admin", nombre="Admin", correo="admin@example.test",
                            hash_contrasena="test", rol="admin"))
        session.commit()
    auth = {"Authorization": f"Bearer {create_token('demo-admin')}"}
    with TestClient(app) as client:
        mission_id: str | None = None
        try:
            assert client.get("/api/v1/missions").status_code == 401

            health = client.get("/api/v1/health")
            assert health.status_code == 200
            assert health.json()["detector"] == "mock"
            assert health.json()["database"] == "postgresql"

            demo = client.post("/api/v1/missions/demo", params={"faena_id": "demo-faena"}, headers=auth)
            assert demo.status_code == 201
            mission = demo.json()
            mission_id = mission["id"]
            assert len(mission["images"]) == 4

            with Session(engine) as session:
                stored_mission = session.get(Mision, mission_id)
                assert stored_mission is not None
                assert stored_mission.id_faena == "demo-faena"

            detected = client.post(f"/api/v1/missions/{mission_id}/detect", headers=auth)
            assert detected.status_code == 200
            payload = detected.json()
            assert payload["status"] == "review"
            assert sum(len(image["detections"]) for image in payload["images"]) >= 4

            report = client.get(f"/api/v1/missions/{mission_id}/report", headers=auth)
            assert report.status_code == 200
            assert report.headers["content-type"] == "application/pdf"
            assert report.content.startswith(b"%PDF")
        finally:
            if mission_id is not None:
                client.delete(f"/api/v1/missions/{mission_id}", headers=auth)
