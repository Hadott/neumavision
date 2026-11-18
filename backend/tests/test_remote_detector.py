import base64
import json
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
from app.services.detector import OFF_ROAD_LABEL, DetectorError, RemoteDetector, overlay_path, width_paths


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


def test_remote_off_road_rocks_and_road_width(tmp_path, monkeypatch):
    import cv2
    import numpy as np

    path = tmp_path / "original.jpg"
    Image.new("RGB", (400, 300), (120, 110, 100)).save(path)
    mask = np.zeros((300, 400), dtype=np.uint8)
    mask[:, 120:280] = 255  # pista vertical de 160 px de ancho
    ok, mask_png = cv2.imencode(".png", mask)
    assert ok
    payload = payload_for(path, detections=[{"alarm": True, "bbox": [150, 100, 170, 120], "confidence": 0.6}])
    payload["off_road_detections"] = [{"alarm": False, "bbox": [10, 10, 30, 30], "confidence": 0.5}]
    payload["segmentation"] = {"confidence": 0.7, "class_id": 2}
    payload["road_mask_png"] = base64.b64encode(mask_png.tobytes()).decode()
    monkeypatch.setattr(settings, "default_gsd_cm_px", 10.0)
    monkeypatch.setattr(httpx, "post", lambda *a, **kw: httpx.Response(
        200, json=payload, request=httpx.Request("POST", "http://inference/predict")))
    findings = RemoteDetector().predict(path)
    assert [item.label for item in findings] == ["Rocas", OFF_ROAD_LABEL]
    jpg_path, json_path = width_paths(path)
    assert jpg_path.is_file() and json_path.is_file()
    summary = json.loads(json_path.read_text(encoding="utf-8"))
    assert summary["clase_pista"] == "Carpeta pedregosa"
    assert 14 <= summary["ancho_mediano_m"] <= 18  # 160 px x 10 cm/px = 16 m

    # una mascara invalida no impide reportar las rocas
    jpg_path.unlink(); json_path.unlink()
    payload["road_mask_png"] = base64.b64encode(b"no es png").decode()
    assert len(RemoteDetector().predict(path)) == 2
    assert not json_path.exists()


def test_remote_saves_width_returned_by_jade(tmp_path, monkeypatch):
    path = tmp_path / "original.jpg"
    Image.new("RGB", (100, 80)).save(path)
    payload = payload_for(path)
    summary = {"estado": "Moderado", "ancho_mediano_m": 24.5}
    payload["road_width"] = {"summary": summary, "overlay_jpeg": payload["overlay_jpeg"]}
    monkeypatch.setattr(settings, "default_gsd_cm_px", 1.2)

    def predict(url, **kwargs):
        assert kwargs["data"] == {"include_road_width": "true", "default_gsd_cm_px": "1.2"}
        return httpx.Response(200, json=payload, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", predict)
    assert len(RemoteDetector().predict(path)) == 1
    jpg_path, json_path = width_paths(path)
    assert jpg_path.read_bytes() == base64.b64decode(payload["overlay_jpeg"])
    assert json.loads(json_path.read_text(encoding="utf-8")) == summary

    payload["road_width"]["overlay_jpeg"] = "invalido"
    assert len(RemoteDetector().predict(path)) == 1
    assert json.loads(json_path.read_text(encoding="utf-8")) == summary


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
        monkeypatch.setattr(settings, "jade_instance_id", "")
        monkeypatch.setattr(settings, "analysis_s3_bucket", "")
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


def test_detection_progress_counts_finished_images(isolated_platform, monkeypatch):
    client, session, path = isolated_platform
    session.add(Imagen(id_imagen="image-2", id_mision="own", nombre_archivo="segunda.jpg",
                      ruta_almacenada=str(path), ancho=100, alto=80))
    session.commit()
    progress_url = "/api/v1/missions/own/detect/progress"
    snapshots = []

    def predict(*args, **kwargs):
        snapshots.append(client.get(progress_url).json())
        return httpx.Response(200, json=payload_for(path), request=httpx.Request("POST", "http://inference/predict"))

    monkeypatch.setattr(httpx, "post", predict)
    assert client.get("/api/v1/missions/other/detect/progress").status_code == 404
    assert client.get(progress_url).json() is None
    assert client.post("/api/v1/missions/own/detect").status_code == 200
    assert [snapshot["completed"] for snapshot in snapshots] == [0, 1]
    assert all(snapshot["total"] == 2 for snapshot in snapshots)
    assert snapshots[0]["estimated_remaining_seconds"] is None
    assert snapshots[1]["estimated_remaining_seconds"] >= 0
    assert client.get(progress_url).json() is None


def test_originals_and_reports_use_private_bucket(isolated_platform, monkeypatch):
    from app.models import Informe
    from app.services import storage

    client, session, path = isolated_platform
    monkeypatch.setattr(settings, "analysis_s3_bucket", "private-test")
    objects = {}

    class Bucket:
        def put_object(self, *, Bucket, Key, Body, ContentType):
            assert Bucket == "private-test"
            objects[Key] = Body if isinstance(Body, bytes) else Body.read()

        def get_object(self, *, Bucket, Key):
            return {"Body": BytesIO(objects[Key])}

    monkeypatch.setattr(storage, "analysis_s3", Bucket)
    response = client.post(
        "/api/v1/missions", data={"name": "Respaldo"},
        files={"files": ("original.jpg", path.read_bytes(), "image/jpeg")},
    )
    assert response.status_code == 201
    mission = response.json()
    image = session.get(Imagen, mission["images"][0]["id"])
    original = Path(image.ruta_almacenada)
    key = storage.original_key(mission["id"], original)
    assert objects[key] == path.read_bytes()
    assert not original.exists()
    assert client.get(mission["images"][0]["image_url"]).content == objects[key]
    with storage.use_original(mission["id"], original):
        assert original.read_bytes() == objects[key]
    assert not original.exists()
    report = client.get(f'/api/v1/missions/{mission["id"]}/report')
    assert report.status_code == 200
    assert report.content.startswith(b"%PDF")
    stored = session.exec(select(Informe)).one()
    assert objects[stored.clave_objeto_s3] == report.content


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


def test_s3_overlay_is_published_only_on_success(isolated_platform, monkeypatch):
    from app.api import missions
    from app.services.storage import AnalysisStorageError

    client, session, path = isolated_platform
    monkeypatch.setattr(settings, "analysis_s3_bucket", "private-test")
    monkeypatch.setattr(httpx, "post", lambda *args, **kwargs: httpx.Response(
        200, json=payload_for(path), request=httpx.Request("POST", "http://inference/predict")))
    objects = {}

    def store(mission_id, image_id, overlay):
        assert (mission_id, image_id) == ("own", "image")
        objects["analysis/result.jpg"] = overlay.read_bytes()
        return "analysis/result.jpg"

    monkeypatch.setattr(missions, "store_analysis", store)
    monkeypatch.setattr(missions, "read_analysis", objects.__getitem__)
    assert client.post("/api/v1/missions/own/detect").status_code == 200
    analysis = "/api/v1/missions/own/images/image?analysis=true"
    assert session.get(Imagen, "image").clave_analisis_s3 == "analysis/result.jpg"
    assert client.get(analysis).content == objects["analysis/result.jpg"]
    assert client.get("/api/v1/missions/other/images/image?analysis=true").status_code == 404

    def unavailable(*args):
        raise AnalysisStorageError("S3 no disponible")

    monkeypatch.setattr(missions, "store_analysis", unavailable)
    assert client.post("/api/v1/missions/own/detect").status_code == 503
    assert session.get(Imagen, "image").clave_analisis_s3 == "analysis/result.jpg"
    assert client.get(analysis).content == objects["analysis/result.jpg"]


def test_half_resolution_preserves_scale_and_overlay_size():
    import numpy as np

    from app.services.ancho_pista import analizar

    mask = np.zeros((301, 401), dtype=np.uint8)
    mask[:, 80:320] = 1
    photo = np.zeros((*mask.shape, 3), dtype=np.uint8)
    _, original = analizar(photo, mask, 10.0, "configurado")
    overlay, reduced = analizar(photo, mask, 10.0, "configurado", media_resolucion=True)

    assert overlay.shape == photo.shape
    assert reduced["gsd_cm_px"] == original["gsd_cm_px"] == 10.0
    assert reduced["ancho_mediano_m"] == pytest.approx(24.0, abs=0.2)
    assert reduced["ancho_min_p10_m"] == pytest.approx(original["ancho_min_p10_m"], abs=0.2)
    assert reduced["estado"] == original["estado"] == "Moderado"
