from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "NeumaDiesel Vision API"
    environment: str = "development"
    api_prefix: str = "/api/v1"
    database_url: str = "postgresql+psycopg://postgres:password@localhost:5432/neumavision"
    upload_dir: Path = Path("./data/uploads")
    detector_mode: str = "mock"
    yolo_model_path: Path = Path("./models/best.pt")
    inference_url: str = "http://127.0.0.1:8001"
    inference_token: str = ""
    inference_timeout: float = Field(default=300, gt=0)
    jade_instance_id: str = Field(default="", pattern=r"^(?:i-[0-9a-f]{8}(?:[0-9a-f]{9})?)?$")
    jade_region: str = "us-east-2"
    jade_start_timeout: float = Field(default=300, gt=0)
    analysis_s3_bucket: str = ""
    # DETECTOR_MODE=neumavision: rocas (YOLO26) + pista (RF-DETR Seg) + ancho de pista
    rock_model_path: Path = Path("./models/rocas.pt")
    road_model_path: Path = Path("./models/pista.pt")
    rock_confidence: float = 0.30      # umbral de operacion elegido (P ~81 %, R ~70 % en test)
    road_confidence: float = 0.20
    road_margin: float = 0.02          # margen alrededor de la pista para aceptar rocas (fraccion de la imagen)
    tile_width: int = 1280             # tiling igual al del entrenamiento (4K -> 3 x 2 tiles de 1280 x 1080)
    tile_height: int = 1080
    default_gsd_cm_px: float | None = None  # se usa si la foto no trae altura en el EXIF
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]
    development_faena_id: str = "00000000-0000-0000-0000-000000000001"
    development_faena_name: str = "NeumaDiesel"
    development_faena_email: str = "neumavision@neumadiesel.com"
    # Clave privada para firmar tokens; debe configurarse en el .env local.
    secret_key: str = Field(min_length=32)
    token_hours: int = 12

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("database_url", mode="before")
    @classmethod
    def use_psycopg3_driver(cls, value: object) -> object:
        if isinstance(value, str) and value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        if isinstance(value, str) and value.startswith("postgresql+psycopg2://"):
            return value.replace("postgresql+psycopg2://", "postgresql+psycopg://", 1)
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
