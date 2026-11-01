from __future__ import annotations

import asyncio
from math import asin, cos, radians, sin, sqrt

from app.schemas import (
    Coordinate, Delivery, DeliveryCreate, Stop, StopCreate, StopKind,
    StopStatus, Vehicle, VehicleCreate, VehicleStatus, _now,
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
        self.deliveries: dict[str, Delivery] = {}
        self._dist: dict[tuple[Coordinate, Coordinate], float] = {}  # memoized matrix
        self.pending: asyncio.Queue[str] = asyncio.Queue()  # stop or delivery IDs
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

    # ----- standalone stops -----
    async def add_stop(self, data: StopCreate) -> Stop:
        s = Stop(**data.model_dump())
        async with self.lock:
            self.stops[s.id] = s
        await self.pending.put(s.id)  # wake the background worker
        return s

    async def assign(self, stop_id: str, vehicle_id: str, index: int | None = None) -> bool:
        async with self.lock:
            return self.assign_locked(stop_id, vehicle_id, index)

    def assign_locked(self, stop_id: str, vehicle_id: str, index: int | None = None) -> bool:
        """Capacity-checked assignment. Caller must hold self.lock."""
        s, v = self.stops.get(stop_id), self.vehicles.get(vehicle_id)
        if not s or not v or s.status is not StopStatus.PENDING:
            return False
        if v.load + s.demand > v.capacity or v.status is VehicleStatus.OFFLINE:
            return False
        v.load += s.demand
        if index is None:
            v.route.append(s.id)
        else:
            v.route.insert(index, s.id)
        v.status = VehicleStatus.EN_ROUTE
        s.status, s.vehicle_id = StopStatus.ASSIGNED, v.id
        return True

    # ----- deliveries (donor pickup -> recipient dropoff) -----
    async def add_delivery(self, data: DeliveryCreate) -> Delivery:
        pu = Stop(location=data.pickup, demand=data.demand,
                  priority=data.priority, kind=StopKind.PICKUP)
        do = Stop(location=data.dropoff, demand=data.demand, priority=data.priority,
                  deadline=data.expires_at, kind=StopKind.DROPOFF)
        d = Delivery(pickup_stop_id=pu.id, dropoff_stop_id=do.id,
                     demand=data.demand, expires_at=data.expires_at)
        pu.delivery_id = do.delivery_id = d.id
        async with self.lock:
            self.stops[pu.id], self.stops[do.id] = pu, do
            self.deliveries[d.id] = d
        await self.pending.put(d.id)
        return d

    def assign_pair_locked(self, d: Delivery, vehicle_id: str, route: list[str]) -> None:
        """Commit a pre-validated route. Caller must hold self.lock."""
        v = self.vehicles[vehicle_id]
        v.route = route
        v.status = VehicleStatus.EN_ROUTE
        for sid in (d.pickup_stop_id, d.dropoff_stop_id):
            s = self.stops[sid]
            s.status, s.vehicle_id = StopStatus.ASSIGNED, vehicle_id
        d.status, d.vehicle_id = StopStatus.ASSIGNED, vehicle_id

    def fail_delivery_locked(self, d: Delivery) -> None:
        d.status = StopStatus.FAILED
        for sid in (d.pickup_stop_id, d.dropoff_stop_id):
            self.stops[sid].status = StopStatus.FAILED


state = LogisticsState()  # module-level singleton
