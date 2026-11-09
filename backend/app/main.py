from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.missions import router as missions_router
from app.api.dashboard import router as dashboard_router
from app.config import settings
from app.database import ensure_development_faena, initialize_database
from app.schemas import HealthRead


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    initialize_database()
    ensure_development_faena()
    yield


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


app.include_router(auth_router, prefix=settings.api_prefix)
app.include_router(missions_router, prefix=settings.api_prefix)
app.include_router(dashboard_router, prefix=settings.api_prefix)
