from sqlalchemy import inspect, text
from sqlmodel import Session, SQLModel, create_engine, select

from app.config import settings
from app.models import Faena


engine = create_engine(settings.database_url, pool_pre_ping=True)


def initialize_database() -> None:
    SQLModel.metadata.create_all(engine)
    _sync_sqlite_columns()
    _backfill_null_defaults()


def _sync_sqlite_columns() -> None:
    """En desarrollo con SQLite, create_all crea tablas nuevas pero no agrega
    columnas nuevas a tablas que ya existen. Sincroniza las columnas que falten
    para que la base local no quede desactualizada respecto de los modelos
    (en produccion con PostgreSQL este ajuste lo maneja Alembic, no esto)."""
    if engine.dialect.name != "sqlite":
        return
    inspector = inspect(engine)
    with engine.begin() as connection:
        for table in SQLModel.metadata.sorted_tables:
            if not inspector.has_table(table.name):
                continue
            existing_columns = {col["name"] for col in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing_columns:
                    continue
                column_type = column.type.compile(engine.dialect)
                default_clause = ""
                if column.default is not None and getattr(column.default, "is_scalar", False):
                    default_clause = f" DEFAULT '{column.default.arg}'"
                connection.execute(
                    text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {column_type}{default_clause}')
                )


def _backfill_null_defaults() -> None:
    """Completa con su valor por defecto las filas que quedaron con NULL en una
    columna agregada por _sync_sqlite_columns antes de tener un DEFAULT aplicado
    (por ejemplo, si el ALTER TABLE se interrumpio a mitad de camino)."""
    if engine.dialect.name != "sqlite":
        return
    with engine.begin() as connection:
        for table in SQLModel.metadata.sorted_tables:
            for column in table.columns:
                if column.default is None or not getattr(column.default, "is_scalar", False):
                    continue
                connection.execute(
                    text(
                        f'UPDATE "{table.name}" SET "{column.name}" = :default_value '
                        f'WHERE "{column.name}" IS NULL'
                    ),
                    {"default_value": column.default.arg},
                )


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
