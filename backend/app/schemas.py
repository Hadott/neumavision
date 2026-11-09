from datetime import datetime
from typing import Literal

from pydantic import BaseModel


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
    detections: list[DetectionRead]
    criticidad_manual: ManualCriticality | None = None


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
