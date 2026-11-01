from datetime import datetime, timedelta, timezone

import pytest
from app.optimizer import route_feasible
from app.schemas import Coordinate, DeliveryCreate, StopKind, StopStatus, VehicleCreate
from app.state import LogisticsState
from app.worker import dispatch_one


def C(lat, lng):
    return Coordinate(lat=lat, lng=lng)


@pytest.mark.asyncio
async def test_pickup_before_dropoff_same_vehicle():
    st = LogisticsState()
    v = await st.add_vehicle(VehicleCreate(location=C(10, 76), capacity=10))
    d = await st.add_delivery(DeliveryCreate(pickup=C(10.1, 76.1), dropoff=C(10.2, 76.2), demand=3))
    assert await dispatch_one(st, d.id) is True
    assert st.vehicles[v.id].route == [d.pickup_stop_id, d.dropoff_stop_id]
    assert st.deliveries[d.id].status is StopStatus.ASSIGNED


@pytest.mark.asyncio
async def test_capacity_forces_sequencing():
    st = LogisticsState()
    v = await st.add_vehicle(VehicleCreate(location=C(10, 76), capacity=5))
    d1 = await st.add_delivery(DeliveryCreate(pickup=C(10.1, 76.1), dropoff=C(10.2, 76.2), demand=4))
    d2 = await st.add_delivery(DeliveryCreate(pickup=C(10.15, 76.1), dropoff=C(10.25, 76.2), demand=4))
    assert await dispatch_one(st, d1.id) and await dispatch_one(st, d2.id)
    route = st.vehicles[v.id].route
    kinds = [st.stops[i].kind for i in route]
    assert kinds == [StopKind.PICKUP, StopKind.DROPOFF] * 2  # 4+4 > 5, so never overlap
    assert route_feasible(st, st.vehicles[v.id], route, datetime.now(timezone.utc))


@pytest.mark.asyncio
async def test_expired_delivery_fails():
    st = LogisticsState()
    await st.add_vehicle(VehicleCreate(location=C(10, 76), capacity=10))
    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    d = await st.add_delivery(DeliveryCreate(
        pickup=C(10.1, 76.1), dropoff=C(10.2, 76.2), demand=1, expires_at=past))
    assert await dispatch_one(st, d.id) is True
    assert st.deliveries[d.id].status is StopStatus.FAILED


@pytest.mark.asyncio
async def test_unreachable_deadline_stays_pending():
    st = LogisticsState()
    await st.add_vehicle(VehicleCreate(location=C(10, 76), capacity=10))
    soon = datetime.now(timezone.utc) + timedelta(minutes=10)  # ~155 km needs ~5 h
    d = await st.add_delivery(DeliveryCreate(
        pickup=C(10, 76), dropoff=C(11, 77), demand=1, expires_at=soon))
    assert await dispatch_one(st, d.id) is False
    assert st.deliveries[d.id].status is StopStatus.PENDING
