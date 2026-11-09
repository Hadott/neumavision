"""Autenticacion por faena con tokens firmados (HMAC-SHA256, sin dependencias externas).

El token contiene el id de la cuenta y su vencimiento. La firma usa SECRET_KEY,
por lo que no puede ser modificado por el cliente sin invalidarse.
"""

import base64
import hashlib
import hmac
import json
import time
from typing import Annotated

from fastapi import Depends, HTTPException, Query, Request, status
from sqlmodel import Session

from app.config import settings
from app.database import get_session
from app.models import Faena

ROL_ADMIN = "admin"
ROL_FAENA = "faena"


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _sign(payload: str) -> str:
    digest = hmac.new(settings.secret_key.encode(), payload.encode(), hashlib.sha256).digest()
    return _b64encode(digest)


def create_token(faena_id: str) -> str:
    expires = int(time.time()) + settings.token_hours * 3600
    payload = _b64encode(json.dumps({"sub": faena_id, "exp": expires}).encode())
    return f"{payload}.{_sign(payload)}"


def read_token(token: str) -> str | None:
    """Devuelve el id de la cuenta si el token es valido y no ha vencido."""
    try:
        payload, signature = token.split(".", 1)
        if not hmac.compare_digest(signature, _sign(payload)):
            return None
        data = json.loads(_b64decode(payload))
        if int(data.get("exp", 0)) < time.time():
            return None
        return str(data["sub"])
    except (ValueError, KeyError, json.JSONDecodeError):
        return None


def get_current_faena(
    request: Request,
    token: str | None = Query(default=None, include_in_schema=False),
    session: Session = Depends(get_session),
) -> Faena:
    """Identifica la cuenta a partir del header Authorization o del parametro ?token=
    (este ultimo se usa en las imagenes, que el navegador carga sin headers)."""
    header = request.headers.get("Authorization", "")
    raw = header[7:] if header.lower().startswith("bearer ") else token
    faena_id = read_token(raw) if raw else None
    faena = session.get(Faena, faena_id) if faena_id else None
    if faena is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesión inválida o vencida. Inicia sesión nuevamente.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return faena


CurrentFaena = Annotated[Faena, Depends(get_current_faena)]


def is_admin(faena: Faena) -> bool:
    return (faena.rol or ROL_FAENA) == ROL_ADMIN
