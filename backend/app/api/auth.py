import re
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pwdlib.exceptions import UnknownHashError
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.database import get_session
from app.models import Faena, Mision, Usuario
from app.services.auth import CurrentFaena, create_token, is_admin
from app.services.passwords import hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])
Password = Annotated[str, Field(min_length=8, max_length=128)]


class LoginRequest(BaseModel):
    correo: str
    contrasena: str


class FaenaWrite(BaseModel):
    nombre: str = Field(min_length=1, max_length=120)


class UserCreate(FaenaWrite):
    correo: str = Field(min_length=3, max_length=255)
    contrasena: Password
    rol: Literal["admin", "operador"] = "operador"
    id_faena: str | None = None


class PasswordReset(BaseModel):
    contrasena: Password


class FaenaRead(BaseModel):
    id: str
    nombre: str
    misiones: int = 0


class AccountRead(BaseModel):
    id: str
    nombre: str
    correo: str
    rol: str
    id_faena: str | None


class LoginResponse(BaseModel):
    token: str
    cuenta: AccountRead


def require_admin(cuenta: CurrentFaena) -> Usuario:
    if not is_admin(cuenta):
        raise HTTPException(403, "Solo disponible para administradores.")
    return cuenta


Admin = Annotated[Usuario, Depends(require_admin)]


def require_faena(session: Session, faena_id: str, *, lock: bool = False) -> Faena:
    faena = session.get(Faena, faena_id, with_for_update=lock)
    if faena is None:
        raise HTTPException(404, "Faena no encontrada.")
    return faena


def normalize_name(nombre: str) -> str:
    nombre = nombre.strip()
    if not nombre:
        raise HTTPException(422, "El nombre es obligatorio.")
    return nombre


def serialize_user(user: Usuario) -> AccountRead:
    return AccountRead(
        id=user.id_usuario, nombre=user.nombre, correo=user.correo, rol=user.rol, id_faena=user.id_faena,
    )


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, session: Session = Depends(get_session)) -> LoginResponse:
    correo = payload.correo.strip().lower()
    user = session.exec(
        select(Usuario).where(Usuario.correo == correo, Usuario.hash_contrasena.is_not(None))
    ).first()
    if user and user.hash_contrasena and (is_admin(user) or user.id_faena):
        try:
            if verify_password(payload.contrasena, user.hash_contrasena):
                return LoginResponse(token=create_token(user.id_usuario), cuenta=serialize_user(user))
        except (UnknownHashError, ValueError):
            pass
    raise HTTPException(401, "Correo o contraseña incorrectos.")


@router.get("/me", response_model=AccountRead)
def me(cuenta: CurrentFaena) -> AccountRead:
    return serialize_user(cuenta)


@router.get("/admin/usuarios", response_model=list[AccountRead])
def list_users(_: Admin, session: Session = Depends(get_session)) -> list[AccountRead]:
    return [serialize_user(user) for user in session.exec(select(Usuario).order_by(Usuario.nombre)).all()]


@router.post("/admin/usuarios", response_model=AccountRead, status_code=201)
def create_user(payload: UserCreate, _: Admin, session: Session = Depends(get_session)) -> AccountRead:
    nombre = normalize_name(payload.nombre)
    correo = payload.correo.strip().lower()
    if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", correo) is None:
        raise HTTPException(422, "Correo electrónico inválido.")
    if payload.rol == "operador":
        if not payload.id_faena:
            raise HTTPException(422, "Selecciona una faena para el operador.")
        require_faena(session, payload.id_faena, lock=True)
    elif payload.id_faena is not None:
        raise HTTPException(422, "El administrador global no requiere una faena.")

    user = Usuario(
        nombre=nombre, correo=correo, hash_contrasena=hash_password(payload.contrasena),
        rol=payload.rol, id_faena=payload.id_faena,
    )
    session.add(user)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(409, "Ese correo ya está asociado a otra cuenta.") from error
    session.refresh(user)
    return serialize_user(user)


@router.put("/admin/usuarios/{user_id}/password", status_code=204)
def reset_password(user_id: str, payload: PasswordReset, _: Admin, session: Session = Depends(get_session)) -> None:
    user = session.get(Usuario, user_id)
    if user is None:
        raise HTTPException(404, "Usuario no encontrado.")
    user.hash_contrasena = hash_password(payload.contrasena)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(409, "Ese correo ya está asociado a otra cuenta.") from error


@router.get("/faenas", response_model=list[FaenaRead])
@router.get("/admin/faenas", response_model=list[FaenaRead])
def list_faenas(_: Admin, session: Session = Depends(get_session)) -> list[FaenaRead]:
    query = (
        select(Faena.id_faena, Faena.nombre, func.count(Mision.id_mision))
        .outerjoin(Mision, Faena.id_faena == Mision.id_faena)
        .group_by(Faena.id_faena, Faena.nombre)
        .order_by(Faena.nombre)
    )
    return [FaenaRead(id=id_faena, nombre=nombre, misiones=count) for id_faena, nombre, count in session.exec(query)]


@router.post("/admin/faenas", response_model=FaenaRead, status_code=201)
def create_faena(payload: FaenaWrite, _: Admin, session: Session = Depends(get_session)) -> FaenaRead:
    faena = Faena(nombre=normalize_name(payload.nombre))
    session.add(faena)
    session.commit()
    session.refresh(faena)
    return FaenaRead(id=faena.id_faena, nombre=faena.nombre)


@router.patch("/admin/faenas/{faena_id}", response_model=FaenaRead)
def update_faena(faena_id: str, payload: FaenaWrite, _: Admin, session: Session = Depends(get_session)) -> FaenaRead:
    faena = require_faena(session, faena_id)
    faena.nombre = normalize_name(payload.nombre)
    session.commit()
    count = session.exec(select(func.count()).select_from(Mision).where(Mision.id_faena == faena_id)).one()
    return FaenaRead(id=faena.id_faena, nombre=faena.nombre, misiones=count)


@router.delete("/admin/faenas/{faena_id}", status_code=204)
def delete_faena(faena_id: str, _: Admin, session: Session = Depends(get_session)) -> None:
    faena = require_faena(session, faena_id, lock=True)
    if session.exec(select(Mision.id_mision).where(Mision.id_faena == faena_id)).first() is not None:
        raise HTTPException(409, "La faena tiene misiones. Elimínalas antes de eliminar la faena.")
    if session.exec(select(Usuario.id_usuario).where(Usuario.id_faena == faena_id)).first() is not None:
        raise HTTPException(409, "La faena tiene operadores asignados.")
    session.delete(faena)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(409, "La faena tiene recursos asociados.") from error
