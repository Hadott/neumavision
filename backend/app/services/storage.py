from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.config import settings


ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}


def ensure_upload_directory() -> Path:
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    return settings.upload_dir


async def save_upload(mission_id: str, upload: UploadFile) -> Path:
    extension = Path(upload.filename or "image.jpg").suffix.lower() or ".jpg"
    mission_directory = ensure_upload_directory() / mission_id
    mission_directory.mkdir(parents=True, exist_ok=True)
    target = mission_directory / f"{uuid4()}{extension}"
    content = await upload.read()
    target.write_bytes(content)
    return target


def mission_directory(mission_id: str) -> Path:
    directory = ensure_upload_directory() / mission_id
    directory.mkdir(parents=True, exist_ok=True)
    return directory
