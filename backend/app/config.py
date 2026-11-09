from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "NeumaDiesel Vision API"
    environment: str = "development"
    api_prefix: str = "/api/v1"
    database_url: str = "postgresql+psycopg://postgres:password@localhost:5432/neumavision"
    upload_dir: Path = Path("./data/uploads")
    detector_mode: str = "mock"
    yolo_model_path: Path = Path("./models/best.pt")
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]
    development_faena_id: str = "00000000-0000-0000-0000-000000000001"
    development_faena_name: str = "NeumaDiesel"
    development_faena_email: str = "neumavision@neumadiesel.com"
    # Clave para firmar los tokens de sesion. En produccion debe definirse en .env.
    secret_key: str = "cambiar-esta-clave-en-produccion"
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
