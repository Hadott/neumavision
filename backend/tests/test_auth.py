from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.database import get_session
from app.main import app
from app.models import Faena
from app.services.auth import get_current_faena
from app.services.passwords import hash_password, verify_password


class FakeSession:
    def __init__(self, target: Faena | None) -> None:
        self.target = target
        self.added: Faena | None = None
        self.committed = False
        self.refreshed: Faena | None = None

    def get(self, model: type[Faena], faena_id: str) -> Faena | None:
        assert model is Faena
        return self.target if self.target and self.target.id_faena == faena_id else None

    def add(self, faena: Faena) -> None:
        self.added = faena

    def commit(self) -> None:
        self.committed = True

    def exec(self, statement: object) -> "FakeResult":
        return FakeResult()

    def refresh(self, faena: Faena) -> None:
        self.refreshed = faena

    def rollback(self) -> None:
        self.committed = False


class FakeResult:
    def first(self) -> None:
        return None


@pytest.fixture
def client_for_role() -> Iterator[tuple[TestClient, FakeSession]]:
    target = Faena(
        id_faena="target-faena",
        nombre="Faena de prueba",
        correo="faena@example.test",
        hash_contrasena=hash_password("old-password"),
        rol="faena",
    )
    session = FakeSession(target)
    actor = Faena(
        id_faena="actor",
        nombre="Administrador de prueba",
        correo="admin@example.test",
        hash_contrasena=hash_password("admin-password"),
        rol="admin",
    )
    app.dependency_overrides[get_current_faena] = lambda: actor
    app.dependency_overrides[get_session] = lambda: session
    try:
        yield TestClient(app), session
    finally:
        app.dependency_overrides.clear()


def test_admin_can_reset_faena_password(client_for_role: tuple[TestClient, FakeSession]) -> None:
    client, session = client_for_role

    response = client.put(
        "/api/v1/auth/faenas/target-faena/password",
        json={"contrasena": "new-password-123"},
    )

    assert response.status_code == 204
    assert session.committed
    assert session.added is session.target
    assert verify_password("new-password-123", session.target.hash_contrasena)
    assert not verify_password("old-password", session.target.hash_contrasena)


def test_password_reset_rejects_non_admin(client_for_role: tuple[TestClient, FakeSession]) -> None:
    client, session = client_for_role
    actor = Faena(
        id_faena="actor",
        nombre="Faena",
        correo="user@example.test",
        hash_contrasena=hash_password("user-password"),
        rol="faena",
    )
    app.dependency_overrides[get_current_faena] = lambda: actor

    response = client.put(
        "/api/v1/auth/faenas/target-faena/password",
        json={"contrasena": "new-password-123"},
    )

    assert response.status_code == 403
    assert not session.committed


def test_password_reset_requires_authentication() -> None:
    app.dependency_overrides[get_session] = lambda: FakeSession(None)
    try:
        response = TestClient(app).put(
            "/api/v1/auth/faenas/target-faena/password",
            json={"contrasena": "new-password-123"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401


def test_password_reset_returns_not_found_for_unknown_faena(
    client_for_role: tuple[TestClient, FakeSession],
) -> None:
    client, session = client_for_role

    response = client.put(
        "/api/v1/auth/faenas/missing/password",
        json={"contrasena": "new-password-123"},
    )

    assert response.status_code == 404
    assert not session.committed


def test_password_reset_validates_minimum_length(
    client_for_role: tuple[TestClient, FakeSession],
) -> None:
    client, session = client_for_role

    response = client.put(
        "/api/v1/auth/faenas/target-faena/password",
        json={"contrasena": "short"},
    )

    assert response.status_code == 422
    assert not session.committed


def test_admin_can_create_faena_account(client_for_role: tuple[TestClient, FakeSession]) -> None:
    client, session = client_for_role

    response = client.post(
        "/api/v1/auth/admin/faenas",
        json={
            "nombre": "Nueva faena",
            "correo": " NUEVA@example.test ",
            "contrasena": "initial-password-123",
        },
    )

    assert response.status_code == 201
    assert response.json()["nombre"] == "Nueva faena"
    assert response.json()["correo"] == "nueva@example.test"
    assert response.json()["rol"] == "faena"
    assert response.json()["misiones"] == 0
    assert session.committed
    assert session.refreshed is session.added
    assert session.added is not None
    assert verify_password("initial-password-123", session.added.hash_contrasena)


def test_create_faena_rejects_non_admin(client_for_role: tuple[TestClient, FakeSession]) -> None:
    client, session = client_for_role
    actor = Faena(
        id_faena="actor",
        nombre="Faena",
        correo="user@example.test",
        hash_contrasena=hash_password("user-password"),
        rol="faena",
    )
    app.dependency_overrides[get_current_faena] = lambda: actor

    response = client.post(
        "/api/v1/auth/admin/faenas",
        json={
            "nombre": "Nueva faena",
            "correo": "nueva@example.test",
            "contrasena": "initial-password-123",
        },
    )

    assert response.status_code == 403
    assert not session.committed


def test_create_faena_validates_password_length(client_for_role: tuple[TestClient, FakeSession]) -> None:
    client, session = client_for_role

    response = client.post(
        "/api/v1/auth/admin/faenas",
        json={"nombre": "Nueva faena", "correo": "nueva@example.test", "contrasena": "short"},
    )

    assert response.status_code == 422
    assert not session.committed


def test_admin_can_update_account_name_and_email(client_for_role: tuple[TestClient, FakeSession]) -> None:
    client, session = client_for_role

    response = client.patch(
        "/api/v1/auth/admin/faenas/target-faena",
        json={"nombre": "Nueva faena", "correo": " NUEVO@example.test "},
    )

    assert response.status_code == 200
    assert response.json()["nombre"] == "Nueva faena"
    assert response.json()["correo"] == "nuevo@example.test"
    assert session.target.nombre == "Nueva faena"
    assert session.target.correo == "nuevo@example.test"
    assert session.committed


def test_account_update_rejects_invalid_email(client_for_role: tuple[TestClient, FakeSession]) -> None:
    client, session = client_for_role

    response = client.patch(
        "/api/v1/auth/admin/faenas/target-faena",
        json={"nombre": "Nueva faena", "correo": "invalid-email"},
    )

    assert response.status_code == 422
    assert not session.committed
