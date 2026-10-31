import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app, lifespan
from app.state import state


@pytest.mark.asyncio
async def test_end_to_end_dispatch():
    state.vehicles.clear()
    state.stops.clear()
    async with lifespan(app):  # starts the background worker
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            v = (await c.post("/vehicles", json={
                "location": {"lat": 10.0, "lng": 76.0}, "capacity": 10})).json()
            s = (await c.post("/stops", json={
                "location": {"lat": 10.1, "lng": 76.1}, "demand": 2})).json()

            for _ in range(50):  # wait up to ~1s for the worker
                if (await c.get(f"/stops/{s['id']}")).json()["status"] == "assigned":
                    break
                await asyncio.sleep(0.02)

            routes = (await c.get("/routes")).json()
            assert routes[0]["vehicle_id"] == v["id"]
            assert [x["id"] for x in routes[0]["stops"]] == [s["id"]]


@pytest.mark.asyncio
async def test_validation_rejects_bad_input():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post("/stops", json={
            "location": {"lat": 999, "lng": 0}, "demand": 1})
        assert r.status_code == 422