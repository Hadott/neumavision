import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.missions import router as missions_router
from app.api.dashboard import router as dashboard_router
from app.config import settings
from app.database import ensure_development_faena, initialize_database
from app.schemas import HealthRead, InferenceHealthRead
from app.services.auth import CurrentFaena, is_admin
from app.services.jade import IDLE_CHECK_SECONDS, jade


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
    initialize_database()
    ensure_development_faena()
    stop = asyncio.Event()
    monitor = None
    if settings.detector_mode == "remote" and settings.jade_instance_id and settings.jade_idle_timeout_seconds:
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
        idle_timeout_seconds=settings.jade_idle_timeout_seconds if managed else None,
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


app.include_router(auth_router, prefix=settings.api_prefix)
app.include_router(missions_router, prefix=settings.api_prefix)
app.include_router(dashboard_router, prefix=settings.api_prefix)
