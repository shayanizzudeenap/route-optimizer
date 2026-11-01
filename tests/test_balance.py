import pytest
from app.schemas import Coordinate, StopCreate, VehicleCreate
from app.state import LogisticsState
from app.worker import balance_penalty, dispatch_one


def C(lat, lng):
    return Coordinate(lat=lat, lng=lng)


async def _dispatch_cluster(balance: float) -> dict[str, int]:
    """Two vehicles at the same spot, six stops clustered ~15 km away."""
    st = LogisticsState()
    st.balance_km_per_stop = balance
    va = await st.add_vehicle(VehicleCreate(location=C(10, 76), capacity=100))
    vb = await st.add_vehicle(VehicleCreate(location=C(10, 76), capacity=100))
    for i in range(6):
        s = await st.add_stop(StopCreate(location=C(10.1 + 0.001 * i, 76.1), demand=1))
        assert await dispatch_one(st, s.id) is True
    return {va.id: len(st.vehicles[va.id].route), vb.id: len(st.vehicles[vb.id].route)}


@pytest.mark.asyncio
async def test_without_balancing_one_vehicle_takes_everything():
    counts = await _dispatch_cluster(balance=0.0)
    assert sorted(counts.values()) == [0, 6]


@pytest.mark.asyncio
async def test_balancing_spreads_stops_across_vehicles():
    counts = await _dispatch_cluster(balance=10.0)
    assert min(counts.values()) >= 1
    assert max(counts.values()) < 6


def test_priority_scales_penalty():
    st = LogisticsState()
    assert balance_penalty(st, 4, 5) < balance_penalty(st, 4, 3) < balance_penalty(st, 4, 1)
    st.balance_km_per_stop = 0.0
    assert balance_penalty(st, 4, 1) == 0.0


@pytest.mark.asyncio
async def test_urgent_stop_takes_nearest_vehicle_despite_load():
    async def run(priority: int) -> bool:
        st = LogisticsState()
        st.balance_km_per_stop = 10.0
        busy = await st.add_vehicle(VehicleCreate(location=C(10, 76), capacity=100))
        await st.add_vehicle(VehicleCreate(location=C(10.3, 76.3), capacity=100))
        for i in range(2):  # give `busy` a route of two nearby stops
            s = await st.add_stop(StopCreate(location=C(10.1, 76.1 + 0.001 * i), demand=1))
            assert await st.assign(s.id, busy.id)
        new = await st.add_stop(StopCreate(location=C(10.1, 76.1), demand=1, priority=priority))
        assert await dispatch_one(st, new.id) is True
        return st.stops[new.id].vehicle_id == busy.id

    assert await run(priority=5) is True    # urgent: nearest vehicle wins
    assert await run(priority=1) is False   # low urgency: goes to the idle vehicle
