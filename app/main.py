from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from app.optimizer import path_length
from app.schemas import (
    LocationUpdate, RouteView, Stop, StopCreate, Vehicle, VehicleCreate,
)
from app.state import state
from app.worker import run_worker


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(run_worker(state))
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="Real-Time Dynamic Route Optimizer",
    description="Continuously re-optimizes delivery routes as vehicles and stops stream in.",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict:
    return {
        "vehicles": len(state.vehicles),
        "stops": len(state.stops),
        "queue_depth": state.pending.qsize(),
    }


@app.post("/vehicles", response_model=Vehicle, status_code=201)
async def create_vehicle(body: VehicleCreate) -> Vehicle:
    return await state.add_vehicle(body)


@app.get("/vehicles", response_model=list[Vehicle])
async def list_vehicles() -> list[Vehicle]:
    return list(state.vehicles.values())


@app.put("/vehicles/{vehicle_id}/location", response_model=Vehicle)
async def update_location(vehicle_id: str, body: LocationUpdate) -> Vehicle:
    v = await state.move_vehicle(vehicle_id, body.location)
    if v is None:
        raise HTTPException(404, "vehicle not found")
    return v


@app.post("/stops", response_model=Stop, status_code=202)
async def create_stop(body: StopCreate) -> Stop:
    return await state.add_stop(body)


@app.get("/stops/{stop_id}", response_model=Stop)
async def get_stop(stop_id: str) -> Stop:
    s = state.stops.get(stop_id)
    if s is None:
        raise HTTPException(404, "stop not found")
    return s


@app.get("/routes", response_model=list[RouteView])
async def get_routes() -> list[RouteView]:
    out = []
    for v in state.vehicles.values():
        out.append(RouteView(
            vehicle_id=v.id,
            stops=[state.stops[sid] for sid in v.route],
            total_distance_km=round(path_length(state, v.location, v.route), 3),
        ))
    return out