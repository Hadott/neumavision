from contextlib import closing
from functools import lru_cache
from pathlib import Path
from uuid import uuid4

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
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


class AnalysisStorageError(RuntimeError):
    pass


@lru_cache
def analysis_s3():
    return boto3.client("s3", config=Config(
        connect_timeout=5, read_timeout=30, retries={"total_max_attempts": 3},
    ))


def store_analysis(mission_id: str, image_id: str, path: Path) -> str:
    key = f"analysis/{mission_id}/{image_id}/{uuid4()}.jpg"
    try:
        with path.open("rb") as stream:
            analysis_s3().put_object(
                Bucket=settings.analysis_s3_bucket, Key=key, Body=stream, ContentType="image/jpeg",
            )
    except (BotoCoreError, ClientError, OSError) as error:
        raise AnalysisStorageError("No se pudo guardar la imagen procesada en S3.") from error
    return key


def read_analysis(key: str) -> bytes:
    try:
        response = analysis_s3().get_object(Bucket=settings.analysis_s3_bucket, Key=key)
        with closing(response["Body"]) as stream:
            return stream.read()
    except (BotoCoreError, ClientError, OSError) as error:
        raise AnalysisStorageError("No se pudo leer la imagen procesada desde S3.") from error
