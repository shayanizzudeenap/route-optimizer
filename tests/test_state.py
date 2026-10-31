import pytest
from app.schemas import Coordinate, StopCreate, VehicleCreate
from app.state import LogisticsState


@pytest.mark.asyncio
async def test_assign_respects_capacity():
    st = LogisticsState()
    v = await st.add_vehicle(VehicleCreate(location=Coordinate(lat=10.3, lng=76.3), capacity=5))
    s1 = await st.add_stop(StopCreate(location=Coordinate(lat=10.0, lng=76.2), demand=4))
    s2 = await st.add_stop(StopCreate(location=Coordinate(lat=9.9, lng=76.3), demand=4))
    assert await st.assign(s1.id, v.id) is True
    assert await st.assign(s2.id, v.id) is False  # over capacity