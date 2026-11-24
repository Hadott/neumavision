from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, StrictBool


ReviewStatus = Literal["pending", "confirmed", "rejected"]
RepairStatus = Literal["pending", "repaired"]
ManualCriticality = Literal["critico", "moderado", "optimo"]


class DetectionRead(BaseModel):
    id: str
    label: str
    confidence: float
    x: float
    y: float
    width: float
    height: float
    review_status: ReviewStatus
    repair_status: RepairStatus
    created_at: datetime


class ImageRead(BaseModel):
    id: str
    filename: str
    width: int
    height: int
    latitude: float | None
    longitude: float | None
    image_url: str
    analysis_url: str | None = None
    detections: list[DetectionRead]
    criticidad_manual: ManualCriticality | None = None
    road_width: "RoadWidthRead | None" = None
    road_width_url: str | None = None


class RoadWidthRead(BaseModel):
    """Resultado del analisis de ancho de pista (modelo de segmentacion)."""
    estado: str
    ancho_min_m: float | None = None
    ancho_mediano_m: float | None = None
    gsd_cm_px: float | None = None
    fuente_gsd: str = ""
    eje_medible_pct: float = 0.0
    confianza_pista: float | None = None
    clase_pista: str | None = None
    resumen_incrustado: bool = True


ImageRead.model_rebuild()


class MissionRead(BaseModel):
    id: str
    name: str
    segment: str
    status: str
    created_at: datetime
    images: list[ImageRead]


class MissionSummary(BaseModel):
    id: str
    name: str
    segment: str
    status: str
    created_at: datetime
    image_count: int
    detection_count: int
    pending_count: int
    confirmed_count: int
    criticidad_critico_count: int = 0
    criticidad_moderado_count: int = 0
    criticidad_optimo_count: int = 0
    faena_id: str = ""
    faena_name: str = ""


class DetectionReview(BaseModel):
    review_status: ReviewStatus


class DetectionRepairUpdate(BaseModel):
    repair_status: RepairStatus


class ImageCriticalityUpdate(BaseModel):
    criticidad_manual: ManualCriticality | None = None


class DashboardFinding(BaseModel):
    id: str
    label: str
    confidence: float
    review_status: ReviewStatus
    repair_status: RepairStatus
    created_at: datetime
    x: float
    y: float
    width: float
    height: float
    image_id: str
    image_filename: str
    image_url: str
    latitude: float | None
    longitude: float | None
    mission_id: str
    mission_name: str
    mission_segment: str
    repaired_at: datetime | None = None
    faena_id: str = ""
    faena_name: str = ""


class HealthRead(BaseModel):
    status: str
    detector: str
    database: str


class InferenceHealthRead(BaseModel):
    status: str
    idle_timeout_seconds: int | None
    start_error: str | None = None


class InferenceAutoShutdownUpdate(BaseModel):
    enabled: StrictBool
    idle_timeout_seconds: int | None = Field(default=None, strict=True, ge=1, le=86400)


class InferenceGpuRead(BaseModel):
    name: str
    count: int
    memory_mib: int


class InferenceInstanceRead(BaseModel):
    instance_type: str
    region: str
    availability_zone: str
    specifications_available: bool = False
    specifications_url: str | None = None
    vcpus: int | None = None
    memory_mib: int | None = None
    gpus: list[InferenceGpuRead] = Field(default_factory=list)
    network_performance: str | None = None
    local_storage_gb: int | None = None


class DetectionProgressRead(BaseModel):
    phase: Literal["starting", "processing", "saving"]
    completed: int
    total: int
    estimated_remaining_seconds: float | None = None
