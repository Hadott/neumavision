from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String
from sqlmodel import Field, SQLModel


def new_id() -> str:
    return str(uuid4())


class Faena(SQLModel, table=True):
    __tablename__ = "faena"

    id_faena: str = Field(default_factory=new_id, sa_column=Column("id_faena", String, primary_key=True))
    nombre: str = Field(sa_column=Column("nombre", String(120), nullable=False, index=True))
    correo: str = Field(sa_column=Column("correo", String(255), nullable=False, unique=True, index=True))
    hash_contrasena: str = Field(sa_column=Column("hash_contrasena", String(255), nullable=False))
    rol: str = Field(default="faena", sa_column=Column("rol", String(20), nullable=False, default="faena", server_default="faena"))
    fecha_creacion: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column("fecha_creacion", DateTime, nullable=False),
    )


class Mision(SQLModel, table=True):
    __tablename__ = "mision"

    id_mision: str = Field(default_factory=new_id, sa_column=Column("id_mision", String, primary_key=True))
    id_faena: str = Field(
        sa_column=Column("id_faena", String, ForeignKey("faena.id_faena"), nullable=False, index=True)
    )
    nombre: str = Field(sa_column=Column("nombre", String(120), nullable=False, index=True))
    tramo: str = Field(default="Sin tramo", sa_column=Column("tramo", String(120), nullable=False))
    estado: str = Field(default="uploaded", sa_column=Column("estado", String(30), nullable=False, index=True))
    fecha_creacion: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column("fecha_creacion", DateTime, nullable=False),
    )


class Imagen(SQLModel, table=True):
    __tablename__ = "imagen"

    id_imagen: str = Field(default_factory=new_id, sa_column=Column("id_imagen", String, primary_key=True))
    id_mision: str = Field(
        sa_column=Column("id_mision", String, ForeignKey("mision.id_mision"), nullable=False, index=True)
    )
    nombre_archivo: str = Field(sa_column=Column("nombre_archivo", String(255), nullable=False))
    ruta_almacenada: str = Field(sa_column=Column("ruta_almacenada", String, nullable=False))
    tipo_contenido: str = Field(default="image/jpeg", sa_column=Column("tipo_contenido", String(80), nullable=False))
    ancho: int = Field(sa_column=Column("ancho", Integer, nullable=False))
    alto: int = Field(sa_column=Column("alto", Integer, nullable=False))
    latitud: float | None = Field(default=None, sa_column=Column("latitud", Float, nullable=True))
    longitud: float | None = Field(default=None, sa_column=Column("longitud", Float, nullable=True))
    altitud: float | None = Field(default=None, sa_column=Column("altitud", Float, nullable=True))
    fecha_captura: datetime | None = Field(default=None, sa_column=Column("fecha_captura", DateTime, nullable=True))
    estado_proceso: str = Field(
        default="pending", sa_column=Column("estado_proceso", String(30), nullable=False, index=True)
    )
    # Clasificacion de criticidad asignada manualmente por el revisor durante la revision
    # (critico / moderado / optimo). Es independiente de la criticidad automatica por
    # confianza que se usa en el Dashboard.
    criticidad_manual: str | None = Field(
        default=None, sa_column=Column("criticidad_manual", String(20), nullable=True)
    )


class Deteccion(SQLModel, table=True):
    __tablename__ = "deteccion"

    id_deteccion: str = Field(default_factory=new_id, sa_column=Column("id_deteccion", String, primary_key=True))
    id_imagen: str = Field(
        sa_column=Column("id_imagen", String, ForeignKey("imagen.id_imagen"), nullable=False, index=True)
    )
    clase: str = Field(sa_column=Column("clase", String(80), nullable=False, index=True))
    confianza: float = Field(sa_column=Column("confianza", Float, nullable=False))
    bbox_x: float = Field(sa_column=Column("bbox_x", Float, nullable=False))
    bbox_y: float = Field(sa_column=Column("bbox_y", Float, nullable=False))
    bbox_ancho: float = Field(sa_column=Column("bbox_ancho", Float, nullable=False))
    bbox_alto: float = Field(sa_column=Column("bbox_alto", Float, nullable=False))
    estado_revision: str = Field(
        default="pending", sa_column=Column("estado_revision", String(30), nullable=False, index=True)
    )
    estado_reparacion: str = Field(
        default="pending", sa_column=Column("estado_reparacion", String(30), nullable=False, index=True)
    )
    fecha_reparacion: datetime | None = Field(
        default=None, sa_column=Column("fecha_reparacion", DateTime, nullable=True)
    )


class Informe(SQLModel, table=True):
    __tablename__ = "informe"

    id_informe: str = Field(default_factory=new_id, sa_column=Column("id_informe", String, primary_key=True))
    id_mision: str = Field(
        sa_column=Column(
            "id_mision", String, ForeignKey("mision.id_mision"), nullable=False, unique=True, index=True
        )
    )
    fecha_generacion: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column("fecha_generacion", DateTime, nullable=False),
    )
    clave_objeto_s3: str = Field(sa_column=Column("clave_objeto_s3", String(1024), nullable=False))
    total_hallazgos: int = Field(default=0, sa_column=Column("total_hallazgos", Integer, nullable=False))
