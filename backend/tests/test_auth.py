from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from app.database import get_session
from app.main import app
from app.models import Faena, Mision, Usuario
from app.services.passwords import hash_password


AUTH = "/api/v1/auth"
MISSIONS = "/api/v1/missions"


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'auth.db'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Usuario(
            nombre="Admin", correo="admin@example.test", rol="admin",
            hash_contrasena=hash_password("admin-password"),
        ))
        session.add_all([Faena(id_faena="norte", nombre="Norte"), Faena(id_faena="sur", nombre="Sur")])
        session.add_all([
            Mision(id_mision="m-norte", id_faena="norte", nombre="Misión norte"),
            Mision(id_mision="m-sur", id_faena="sur", nombre="Misión sur"),
        ])
        session.commit()

    def get_test_session():
        with Session(engine) as session:
            yield session

    monkeypatch.setitem(app.dependency_overrides, get_session, get_test_session)
    try:
        yield TestClient(app)
    finally:
        engine.dispose()


def login(client: TestClient, correo: str, password: str) -> tuple[dict, dict[str, str]]:
    response = client.post(f"{AUTH}/login", json={"correo": correo, "contrasena": password})
    assert response.status_code == 200
    result = response.json()
    return result["cuenta"], {"Authorization": f"Bearer {result['token']}"}


def test_faenas_have_no_credentials(client: TestClient) -> None:
    admin, headers = login(client, "admin@example.test", "admin-password")
    assert admin["rol"] == "admin"
    assert admin["id_faena"] is None
    assert client.get(f"{AUTH}/faenas").status_code == 401

    created = client.post(f"{AUTH}/admin/faenas", json={"nombre": " Nueva "}, headers=headers)
    assert created.status_code == 201
    faena_id = created.json()["id"]
    assert created.json() == {"id": faena_id, "nombre": "Nueva", "misiones": 0}
    path = f"{AUTH}/admin/faenas/{faena_id}"
    assert client.patch(path, json={"nombre": " "}, headers=headers).status_code == 422
    assert client.patch(path, json={"nombre": "Renombrada"}, headers=headers).json()["nombre"] == "Renombrada"
    assert client.delete(path, headers=headers).status_code == 204
    assert client.delete(path, headers=headers).status_code == 404
    assert client.delete(f"{AUTH}/admin/faenas/norte", headers=headers).status_code == 409


def test_operators_share_only_their_faena_missions(client: TestClient) -> None:
    _, admin_headers = login(client, "admin@example.test", "admin-password")
    path = f"{AUTH}/admin/usuarios"
    for nombre in ("Ana", "Luis"):
        correo = f"{nombre.lower()}@example.test"
        payload = {"nombre": nombre, "correo": f" {correo.upper()} ", "contrasena": "operador-password"}
        assert client.post(path, json=payload, headers=admin_headers).status_code == 422
        assert client.post(path, json={**payload, "id_faena": "missing"}, headers=admin_headers).status_code == 404

        payload["id_faena"] = "norte"
        created = client.post(path, json=payload, headers=admin_headers)
        assert created.status_code == 201
        assert "hash_contrasena" not in created.json()
        assert client.post(path, json=payload, headers=admin_headers).status_code == 409
        cuenta, headers = login(client, correo, "operador-password")
        assert cuenta == created.json()
        assert cuenta["rol"] == "operador"
        assert client.get(f"{AUTH}/me", headers=headers).json() == cuenta
        assert client.get(path, headers=headers).status_code == 403
        assert client.post(path, json=payload, headers=headers).status_code == 403
        assert client.post(f"{AUTH}/admin/faenas", json={"nombre": "Otra"}, headers=headers).status_code == 403
        assert client.get(f"{MISSIONS}/m-norte", headers=headers).status_code == 200
        assert client.get(f"{MISSIONS}/m-sur", headers=headers).status_code == 404
        listed = client.get(MISSIONS, params={"faena_id": "sur"}, headers=headers)
        assert [mission["id"] for mission in listed.json()] == ["m-norte"]

        reset = f"{path}/{cuenta['id']}/password"
        assert client.put(reset, json={"contrasena": "new-password"}, headers=headers).status_code == 403
        assert client.put(reset, json={"contrasena": "short"}, headers=admin_headers).status_code == 422
        assert client.put(reset, json={"contrasena": "new-password"}, headers=admin_headers).status_code == 204
        assert client.post(f"{AUTH}/login", json={"correo": correo, "contrasena": "operador-password"}).status_code == 401
        login(client, correo, "new-password")

    listed = client.get(path, headers=admin_headers)
    assert [user["nombre"] for user in listed.json()] == ["Admin", "Ana", "Luis"]


def test_admin_user_can_manage_all_faenas(client: TestClient) -> None:
    _, headers = login(client, "admin@example.test", "admin-password")
    payload = {
        "nombre": "Otro Admin", "correo": "otro@example.test", "contrasena": "admin-password", "rol": "admin",
    }
    path = f"{AUTH}/admin/usuarios"
    assert client.post(path, json={**payload, "id_faena": "sur"}, headers=headers).status_code == 422
    response = client.post(path, json=payload, headers=headers)
    assert response.status_code == 201
    assert response.json()["id_faena"] is None
    _, global_headers = login(client, "otro@example.test", "admin-password")
    assert client.get(f"{MISSIONS}/m-norte", headers=global_headers).status_code == 200
    assert client.get(f"{MISSIONS}/m-sur", headers=global_headers).status_code == 200
