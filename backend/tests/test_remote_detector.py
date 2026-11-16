import base64
from io import BytesIO
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.config import settings
from app.database import get_session
from app.main import app
from app.models import Deteccion, Faena, Imagen, Mision
from app.services.auth import get_current_faena
from app.services.detector import DetectorError, RemoteDetector, overlay_path


def payload_for(path: Path, detections=None):
    with Image.open(path) as image:
        width, height = image.size
        buffer = BytesIO()
        image.save(buffer, format="JPEG")
    return {"width": width, "height": height,
            "detections": detections if detections is not None else [
                {"alarm": True, "bbox": [10, 10, 30, 40], "confidence": 0.4}],
            "overlay_jpeg": base64.b64encode(buffer.getvalue()).decode()}


def test_remote_conversion_empty_and_invalid_payload(tmp_path, monkeypatch):
    path = tmp_path / "original.jpg"
    Image.new("RGB", (100, 80)).save(path)
    payload = payload_for(path)
    monkeypatch.setattr(httpx, "post", lambda *a, **kw: httpx.Response(
        200, json=payload, request=httpx.Request("POST", "http://inference/predict")))
    findings = RemoteDetector().predict(path)
    assert len(findings) == 1
    assert findings[0].label == "Rocas"
    assert (findings[0].x, findings[0].y, findings[0].width, findings[0].height) == (0.1, 0.125, 0.2, 0.375)
    assert overlay_path(path).is_file()
    payload["detections"] = []
    assert RemoteDetector().predict(path) == []
    payload["detections"] = [{"alarm": False}]
    with pytest.raises(DetectorError):
        RemoteDetector().predict(path)


@pytest.fixture
def isolated_platform(tmp_path, monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    actor = Faena(id_faena="mine-a", nombre="A", correo="a@test.cl", hash_contrasena="test", rol="faena")
    with Session(engine) as session:
        session.add(actor)
        session.add(Faena(id_faena="mine-b", nombre="B", correo="b@test.cl", hash_contrasena="test", rol="faena"))
        session.add(Mision(id_mision="own", id_faena="mine-a", nombre="Propia"))
        session.add(Mision(id_mision="other", id_faena="mine-b", nombre="Ajena"))
        path = tmp_path / "original.jpg"
        Image.new("RGB", (100, 80)).save(path)
        session.add(Imagen(id_imagen="image", id_mision="own", nombre_archivo="original.jpg",
                          ruta_almacenada=str(path), ancho=100, alto=80))
        session.commit()
        app.dependency_overrides[get_session] = lambda: session
        app.dependency_overrides[get_current_faena] = lambda: actor
        monkeypatch.setattr(settings, "detector_mode", "remote")
        try:
            yield TestClient(app), session, path
        finally:
            app.dependency_overrides.clear()
    engine.dispose()


def test_platform_success_ownership_and_inference_failure(isolated_platform, monkeypatch):
    client, session, path = isolated_platform
    monkeypatch.setattr(httpx, "post", lambda *a, **kw: httpx.Response(
        200, json=payload_for(path), request=httpx.Request("POST", "http://inference/predict")))
    response = client.post("/api/v1/missions/own/detect")
    assert response.status_code == 200
    assert len(response.json()["images"][0]["detections"]) == 1
    assert response.json()["images"][0]["analysis_url"].endswith("?analysis=true")
    assert client.get("/api/v1/missions/own/images/image?analysis=true").status_code == 200
    assert client.post("/api/v1/missions/other/detect").status_code == 404
    assert client.get("/api/v1/missions/other/images/image?analysis=true").status_code == 404
    assert client.post("/api/v1/missions/missing/detect").status_code == 404
    def unavailable(*args, **kwargs):
        raise httpx.ConnectError("inference unavailable")
    monkeypatch.setattr(httpx, "post", unavailable)
    assert client.post("/api/v1/missions/own/detect").status_code == 502
    assert len(session.exec(select(Deteccion)).all()) == 1


def test_platform_zero_findings_and_database_failure(isolated_platform, monkeypatch):
    client, session, path = isolated_platform
    monkeypatch.setattr(httpx, "post", lambda *a, **kw: httpx.Response(
        200, json=payload_for(path, []), request=httpx.Request("POST", "http://inference/predict")))
    response = client.post("/api/v1/missions/own/detect")
    assert response.status_code == 200
    assert response.json()["images"][0]["detections"] == []
    def failed_commit():
        raise SQLAlchemyError("database unavailable")
    monkeypatch.setattr(session, "commit", failed_commit)
    assert client.post("/api/v1/missions/own/detect").status_code == 503
