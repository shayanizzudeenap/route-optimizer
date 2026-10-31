from __future__ import annotations

import asyncio
from math import asin, cos, radians, sin, sqrt

from app.schemas import (
    Coordinate, Stop, StopCreate, StopStatus,
    Vehicle, VehicleCreate, VehicleStatus, _now,
)


def haversine_km(a: Coordinate, b: Coordinate) -> float:
    dlat, dlng = radians(b.lat - a.lat), radians(b.lng - a.lng)
    h = sin(dlat / 2) ** 2 + cos(radians(a.lat)) * cos(radians(b.lat)) * sin(dlng / 2) ** 2
    return 2 * 6371.0088 * asin(sqrt(h))


class LogisticsState:
    """Single-process in-memory engine. All lookups are O(1) dict hits."""

    def __init__(self) -> None:
        self.vehicles: dict[str, Vehicle] = {}
        self.stops: dict[str, Stop] = {}
        self._dist: dict[tuple[Coordinate, Coordinate], float] = {}  # memoized matrix
        self.pending: asyncio.Queue[str] = asyncio.Queue()  # stop IDs for the worker
        self.lock = asyncio.Lock()  # guards multi-step mutations

    # ----- distance matrix (lazy, memoized, symmetric) -----
    def distance(self, a: Coordinate, b: Coordinate) -> float:
        key = (a, b)
        d = self._dist.get(key)
        if d is None:
            d = haversine_km(a, b)
            self._dist[key] = self._dist[(b, a)] = d
        return d

    # ----- vehicles -----
    async def add_vehicle(self, data: VehicleCreate) -> Vehicle:
        v = Vehicle(location=data.location, capacity=data.capacity)
        async with self.lock:
            self.vehicles[v.id] = v
        return v

    async def move_vehicle(self, vehicle_id: str, loc: Coordinate) -> Vehicle | None:
        async with self.lock:
            v = self.vehicles.get(vehicle_id)
            if v is None:
                return None
            v.location = loc
            v.updated_at = _now()
            return v

    # ----- stops -----
    async def add_stop(self, data: StopCreate) -> Stop:
        s = Stop(**data.model_dump())
        async with self.lock:
            self.stops[s.id] = s
        await self.pending.put(s.id)  # wake the background worker
        return s

    async def assign(self, stop_id: str, vehicle_id: str) -> bool:
        """Atomic capacity-checked assignment."""
        async with self.lock:
            s, v = self.stops.get(stop_id), self.vehicles.get(vehicle_id)
            if not s or not v or s.status is not StopStatus.PENDING:
                return False
            if v.load + s.demand > v.capacity or v.status is VehicleStatus.OFFLINE:
                return False
            v.load += s.demand
            v.route.append(s.id)
            v.status = VehicleStatus.EN_ROUTE
            s.status, s.vehicle_id = StopStatus.ASSIGNED, v.id
            return True


state = LogisticsState()  # module-level singleton