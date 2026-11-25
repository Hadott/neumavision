import asyncio
import logging
from contextlib import asynccontextmanager

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.missions import router as missions_router
from app.api.dashboard import router as dashboard_router
from app.config import settings
from app.schemas import HealthRead, InferenceAutoShutdownUpdate, InferenceHealthRead, InferenceInstanceRead
from app.services.auth import CurrentFaena, is_admin
from app.services.jade import IDLE_CHECK_SECONDS, JadeBusy, JadeUnavailable, jade

logger = logging.getLogger(__name__)


async def monitor_jade(stop: asyncio.Event) -> None:
    while not stop.is_set():
        await asyncio.to_thread(jade.stop_if_idle)
        try:
            await asyncio.wait_for(stop.wait(), timeout=IDLE_CHECK_SECONDS)
        except TimeoutError:
            continue


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    stop = asyncio.Event()
    monitor = None
    if settings.detector_mode == "remote" and settings.jade_instance_id:
        monitor = asyncio.create_task(monitor_jade(stop))
    try:
        yield
    finally:
        if monitor:
            stop.set()
            await monitor


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="API for RGB road inspection missions and detection review.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get(f"{settings.api_prefix}/health", response_model=HealthRead, tags=["system"])
def health() -> HealthRead:
    return HealthRead(status="ok", detector=settings.detector_mode, database="postgresql")


@app.get(f"{settings.api_prefix}/inference/health", response_model=InferenceHealthRead, tags=["system"])
def inference_health(cuenta: CurrentFaena) -> InferenceHealthRead:
    managed = settings.detector_mode == "remote" and bool(settings.jade_instance_id)
    status = jade.status()
    return InferenceHealthRead(
        status=status,
        idle_timeout_seconds=jade.idle_timeout_seconds if managed else None,
        start_error=jade.manual_start_error if managed and status != "up" else None,
    )


@app.post(f"{settings.api_prefix}/inference/start", status_code=202, tags=["system"])
def start_inference(cuenta: CurrentFaena) -> dict[str, str]:
    if not is_admin(cuenta):
        raise HTTPException(403, "Solo un administrador puede encender Jade.")
    if settings.detector_mode != "remote" or not settings.jade_instance_id:
        raise HTTPException(409, "El encendido de Jade no está configurado.")
    jade.request_start()
    return {"status": "accepted"}


@app.post(f"{settings.api_prefix}/inference/stop", status_code=202, tags=["system"])
def stop_inference(cuenta: CurrentFaena) -> dict[str, str]:
    if not is_admin(cuenta):
        raise HTTPException(403, "Solo un administrador puede apagar Jade.")
    if settings.detector_mode != "remote" or not settings.jade_instance_id:
        raise HTTPException(409, "El apagado de Jade no está configurado.")
    try:
        stopping = jade.request_stop()
    except JadeBusy as error:
        raise HTTPException(409, str(error)) from error
    except (BotoCoreError, ClientError) as error:
        logger.exception("No se pudo apagar Jade")
        raise HTTPException(503, "AWS no permitió apagar Jade. Intenta de nuevo en un momento.") from error
    return {"status": "stopping" if stopping else "already_stopped"}


@app.put(f"{settings.api_prefix}/inference/auto-shutdown", tags=["system"])
def update_inference_auto_shutdown(payload: InferenceAutoShutdownUpdate, cuenta: CurrentFaena) -> dict[str, int]:
    if not is_admin(cuenta):
        raise HTTPException(403, "Solo un administrador puede configurar el apagado automático de Jade.")
    if settings.detector_mode != "remote" or not settings.jade_instance_id:
        raise HTTPException(409, "La administración de Jade no está configurada.")
    return {"idle_timeout_seconds": jade.set_auto_shutdown(payload.enabled, payload.idle_timeout_seconds)}


@app.get(f"{settings.api_prefix}/inference/instance", response_model=InferenceInstanceRead, tags=["system"])
def inference_instance(cuenta: CurrentFaena) -> InferenceInstanceRead:
    if not is_admin(cuenta):
        raise HTTPException(403, "Solo un administrador puede consultar la instancia de Jade.")
    if settings.detector_mode != "remote" or not settings.jade_instance_id:
        raise HTTPException(409, "La administración de Jade no está configurada.")
    try:
        return jade.instance_details()
    except JadeUnavailable as error:
        raise HTTPException(502, str(error)) from error


app.include_router(auth_router, prefix=settings.api_prefix)
app.include_router(missions_router, prefix=settings.api_prefix)
app.include_router(dashboard_router, prefix=settings.api_prefix)
