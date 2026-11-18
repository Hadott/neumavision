import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.missions import router as missions_router
from app.api.dashboard import router as dashboard_router
from app.config import settings
from app.database import ensure_development_faena, initialize_database
from app.schemas import HealthRead, InferenceHealthRead
from app.services.auth import CurrentFaena
from app.services.jade import IDLE_CHECK_SECONDS, IDLE_TIMEOUT_SECONDS, jade


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
    return InferenceHealthRead(
        status=jade.status(), idle_timeout_seconds=IDLE_TIMEOUT_SECONDS if managed else None,
    )


app.include_router(auth_router, prefix=settings.api_prefix)
app.include_router(missions_router, prefix=settings.api_prefix)
app.include_router(dashboard_router, prefix=settings.api_prefix)
