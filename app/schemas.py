from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uid() -> str:
    return uuid4().hex


class VehicleStatus(str, Enum):
    IDLE = "idle"
    EN_ROUTE = "en_route"
    OFFLINE = "offline"


class StopStatus(str, Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    COMPLETED = "completed"
    FAILED = "failed"


class Coordinate(BaseModel):
    model_config = ConfigDict(frozen=True)  # hashable -> usable as dict key
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


# ---------- Inbound payloads ----------
class VehicleCreate(BaseModel):
    location: Coordinate
    capacity: int = Field(gt=0)


class StopCreate(BaseModel):
    location: Coordinate
    demand: int = Field(gt=0)
    priority: int = Field(default=3, ge=1, le=5)  # 5 = most urgent
    deadline: datetime | None = None


class LocationUpdate(BaseModel):
    location: Coordinate


# ---------- Internal / outbound models ----------
class Vehicle(BaseModel):
    id: str = Field(default_factory=_uid)
    location: Coordinate
    capacity: int
    load: int = 0
    status: VehicleStatus = VehicleStatus.IDLE
    route: list[str] = Field(default_factory=list)  # ordered stop IDs
    updated_at: datetime = Field(default_factory=_now)


class Stop(BaseModel):
    id: str = Field(default_factory=_uid)
    location: Coordinate
    demand: int
    priority: int = 3
    deadline: datetime | None = None
    status: StopStatus = StopStatus.PENDING
    vehicle_id: str | None = None
    created_at: datetime = Field(default_factory=_now)


class RouteView(BaseModel):
    vehicle_id: str
    stops: list[Stop]
    total_distance_km: float