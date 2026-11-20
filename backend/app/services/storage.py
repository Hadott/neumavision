from contextlib import closing, contextmanager
from functools import lru_cache
from pathlib import Path, PureWindowsPath
from tempfile import NamedTemporaryFile
from threading import Lock
from typing import BinaryIO
from uuid import uuid4

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import UploadFile

from app.config import settings


ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
_original_lock = Lock()
_temporary_originals: dict[Path, int] = {}


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
            store_object(key, stream, "image/jpeg")
    except (AnalysisStorageError, OSError) as error:
        raise AnalysisStorageError("No se pudo guardar la imagen procesada en S3.") from error
    return key


def original_key(mission_id: str, path: Path) -> str:
    return f"originals/{mission_id}/{PureWindowsPath(path.name).name}"


def store_original(mission_id: str, path: Path, content_type: str) -> None:
    with path.open("rb") as stream:
        store_object(original_key(mission_id, path), stream, content_type)


def _restore_original(mission_id: str, path: Path) -> None:
    content = read_analysis(original_key(mission_id, path))
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            try:
                stream.write(content)
                stream.close()
                temporary.replace(path)
            finally:
                temporary.unlink(missing_ok=True)
    except OSError as error:
        raise AnalysisStorageError("No se pudo preparar la imagen original en la plataforma.") from error


@contextmanager
def use_original(mission_id: str, path: Path):
    path = path.resolve()
    with _original_lock:
        if path in _temporary_originals:
            _temporary_originals[path] += 1
        elif settings.analysis_s3_bucket and not path.is_file():
            _restore_original(mission_id, path)
            _temporary_originals[path] = 1
    try:
        yield path
    finally:
        with _original_lock:
            users = _temporary_originals.get(path)
            if users == 1:
                del _temporary_originals[path]
                path.unlink(missing_ok=True)
            elif users is not None:
                _temporary_originals[path] = users - 1


def store_object(key: str, body: bytes | BinaryIO, content_type: str) -> None:
    try:
        analysis_s3().put_object(
            Bucket=settings.analysis_s3_bucket, Key=key, Body=body, ContentType=content_type,
        )
    except (BotoCoreError, ClientError, OSError) as error:
        raise AnalysisStorageError("No se pudo guardar el archivo en S3.") from error


def read_analysis(key: str) -> bytes:
    try:
        response = analysis_s3().get_object(Bucket=settings.analysis_s3_bucket, Key=key)
        with closing(response["Body"]) as stream:
            return stream.read()
    except (BotoCoreError, ClientError, OSError) as error:
        raise AnalysisStorageError("No se pudo leer el archivo desde S3.") from error
