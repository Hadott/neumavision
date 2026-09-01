from datetime import datetime
from typing import Literal

from pydantic import BaseModel


ReviewStatus = Literal["pending", "confirmed", "rejected"]


class DetectionRead(BaseModel):
    id: str
    label: str
    confidence: float
    x: float
    y: float
    width: float
    height: float
    review_status: ReviewStatus


class ImageRead(BaseModel):
    id: str
    filename: str
    width: int
    height: int
    latitude: float | None
    longitude: float | None
    image_url: str
    detections: list[DetectionRead]


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


class DetectionReview(BaseModel):
    review_status: ReviewStatus


class HealthRead(BaseModel):
    status: str
    detector: str
    database: str
