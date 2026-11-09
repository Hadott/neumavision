from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session, select

from app.database import get_session
from app.models import Faena
from app.services.auth import CurrentFaena, create_token, is_admin
from app.services.passwords import verify_password


router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    correo: str
    contrasena: str


class AccountRead(BaseModel):
    id: str
    nombre: str
    correo: str
    rol: str


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
