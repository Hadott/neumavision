from sqlmodel import Session, create_engine, select

from app.config import settings
from app.models import Faena


engine = create_engine(settings.database_url, pool_pre_ping=True)


def ensure_development_faena() -> None:
    with Session(engine) as session:
        faena = session.exec(select(Faena).where(Faena.id_faena == settings.development_faena_id)).first()
        if faena is None:
            session.add(
                Faena(
                    id_faena=settings.development_faena_id,
                    nombre=settings.development_faena_name,
                    correo=settings.development_faena_email,
                    hash_contrasena="authentication-not-implemented",
                )
            )
            session.commit()


def get_session():
    with Session(engine) as session:
        yield session
