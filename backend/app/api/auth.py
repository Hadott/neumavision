import re

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.database import get_session
from app.models import Faena, Mision
from app.services.auth import CurrentFaena, create_token, is_admin
from app.services.passwords import hash_password, verify_password


router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    correo: str
    contrasena: str


class PasswordResetRequest(BaseModel):
    contrasena: str = Field(min_length=8, max_length=128)


class AccountUpdateRequest(BaseModel):
    nombre: str = Field(min_length=1, max_length=120)
    correo: str = Field(min_length=3, max_length=255)


class AccountCreateRequest(AccountUpdateRequest):
    contrasena: str = Field(min_length=8, max_length=128)


class AccountRead(BaseModel):
    id: str
    nombre: str
    correo: str
    rol: str


class AdminAccountRead(AccountRead):
    misiones: int


class LoginResponse(BaseModel):
    token: str
    cuenta: AccountRead


def serialize_account(faena: Faena) -> AccountRead:
    return AccountRead(id=faena.id_faena, nombre=faena.nombre, correo=faena.correo, rol=faena.rol or "faena")


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, session: Session = Depends(get_session)) -> LoginResponse:
    correo = payload.correo.strip().lower()
    faena = session.exec(select(Faena).where(Faena.correo == correo)).first()
    valid = False
    if faena is not None:
        try:
            valid = verify_password(payload.contrasena, faena.hash_contrasena)
        except Exception:
            # Cuentas sin contraseña configurada (hash no valido) no pueden iniciar sesion.
            valid = False
    if not valid or faena is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Correo o contraseña incorrectos.")
    return LoginResponse(token=create_token(faena.id_faena), cuenta=serialize_account(faena))


@router.get("/me", response_model=AccountRead)
def me(cuenta: CurrentFaena) -> AccountRead:
    return serialize_account(cuenta)


@router.get("/faenas", response_model=list[AccountRead])
def list_faenas(cuenta: CurrentFaena, session: Session = Depends(get_session)) -> list[AccountRead]:
    """Lista de faenas cliente (solo administrador), para filtrar y asignar misiones."""
    if not is_admin(cuenta):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo disponible para administradores.")
    faenas = session.exec(select(Faena).order_by(Faena.nombre)).all()
    return [serialize_account(item) for item in faenas if (item.rol or "faena") != "admin"]


@router.get("/admin/faenas", response_model=list[AdminAccountRead])
def list_admin_faenas(cuenta: CurrentFaena, session: Session = Depends(get_session)) -> list[AdminAccountRead]:
    if not is_admin(cuenta):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo disponible para administradores.")

    faenas = session.exec(select(Faena).order_by(Faena.nombre)).all()
    mission_counts = dict(
        session.exec(select(Mision.id_faena, func.count(Mision.id_mision)).group_by(Mision.id_faena)).all()
    )
    return [
        AdminAccountRead(
            **serialize_account(faena).model_dump(),
            misiones=mission_counts.get(faena.id_faena, 0),
        )
        for faena in faenas
    ]


@router.post("/admin/faenas", response_model=AdminAccountRead, status_code=status.HTTP_201_CREATED)
def create_faena(
    payload: AccountCreateRequest,
    cuenta: CurrentFaena,
    session: Session = Depends(get_session),
) -> AdminAccountRead:
    if not is_admin(cuenta):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo disponible para administradores.")

    nombre = payload.nombre.strip()
    correo = payload.correo.strip().lower()
    if not nombre:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="El nombre es obligatorio.")
    if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", correo) is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Correo electrónico inválido.")
    if session.exec(select(Faena).where(Faena.correo == correo)).first() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ese correo ya está asociado a otra cuenta.")

    faena = Faena(
        nombre=nombre,
        correo=correo,
        hash_contrasena=hash_password(payload.contrasena),
        rol="faena",
    )
    session.add(faena)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ese correo ya está asociado a otra cuenta.",
        ) from error
    session.refresh(faena)
    return AdminAccountRead(**serialize_account(faena).model_dump(), misiones=0)


@router.patch("/admin/faenas/{faena_id}", response_model=AccountRead)
def update_faena(
    faena_id: str,
    payload: AccountUpdateRequest,
    cuenta: CurrentFaena,
    session: Session = Depends(get_session),
) -> AccountRead:
    if not is_admin(cuenta):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo disponible para administradores.")

    faena = session.get(Faena, faena_id)
    if faena is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Faena no encontrada.")

    nombre = payload.nombre.strip()
    correo = payload.correo.strip().lower()
    if not nombre:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="El nombre es obligatorio.")
    if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", correo) is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Correo electrónico inválido.")

    existing = session.exec(select(Faena).where(Faena.correo == correo, Faena.id_faena != faena_id)).first()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ese correo ya está asociado a otra cuenta.")

    faena.nombre = nombre
    faena.correo = correo
    session.add(faena)
    session.commit()
    session.refresh(faena)
    return serialize_account(faena)


@router.put("/faenas/{faena_id}/password", status_code=status.HTTP_204_NO_CONTENT)
def reset_faena_password(
    faena_id: str,
    payload: PasswordResetRequest,
    cuenta: CurrentFaena,
    session: Session = Depends(get_session),
) -> None:
    """Permite a un administrador asignar una contraseña nueva a una faena."""
    if not is_admin(cuenta):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo disponible para administradores.")

    faena = session.get(Faena, faena_id)
    if faena is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Faena no encontrada.")

    faena.hash_contrasena = hash_password(payload.contrasena)
    session.add(faena)
    session.commit()
