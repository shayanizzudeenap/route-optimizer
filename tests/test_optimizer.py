import pytest
from app.optimizer import path_length, two_opt
from app.schemas import Coordinate, StopCreate, VehicleCreate
from app.state import LogisticsState
from app.worker import dispatch_one


@pytest.mark.asyncio
async def test_two_opt_fixes_zigzag():
    st = LogisticsState()
    ids = []
    for lng in (1, 3, 2):  # deliberately out of order
        s = await st.add_stop(StopCreate(location=Coordinate(lat=0, lng=lng), demand=1))
        ids.append(s.id)
    start = Coordinate(lat=0, lng=0)
    out = two_opt(st, start, ids)
    assert path_length(st, start, out) < path_length(st, start, ids)
    assert [st.stops[i].location.lng for i in out] == [1, 2, 3]


@pytest.mark.asyncio
async def test_dispatch_picks_nearest_vehicle():
    st = LogisticsState()
    near = await st.add_vehicle(VehicleCreate(location=Coordinate(lat=10.0, lng=76.0), capacity=10))
    await st.add_vehicle(VehicleCreate(location=Coordinate(lat=20.0, lng=80.0), capacity=10))
    s = await st.add_stop(StopCreate(location=Coordinate(lat=10.1, lng=76.1), demand=1))
    assert await dispatch_one(st, s.id) is True
    assert st.stops[s.id].vehicle_id == near.id