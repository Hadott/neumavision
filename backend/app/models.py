from datetime import UTC, datetime
from uuid import uuid4

from sqlmodel import Field, SQLModel


def new_id() -> str:
    return str(uuid4())


class Mission(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    name: str = Field(index=True, max_length=120)
    segment: str = Field(default="Sin tramo", max_length=120)
    status: str = Field(default="uploaded", index=True, max_length=30)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class MissionImage(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    mission_id: str = Field(foreign_key="mission.id", index=True)
    filename: str = Field(max_length=255)
    stored_path: str
    content_type: str = Field(default="image/jpeg", max_length=80)
    width: int
    height: int
    latitude: float | None = None
    longitude: float | None = None


class Detection(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    image_id: str = Field(foreign_key="missionimage.id", index=True)
    label: str = Field(index=True, max_length=80)
    confidence: float
    x: float
    y: float
    width: float
    height: float
    review_status: str = Field(default="pending", index=True, max_length=30)
