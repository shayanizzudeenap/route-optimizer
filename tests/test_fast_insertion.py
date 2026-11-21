"""The fast pair insertion must agree with the original brute-force version.

`reference_best_pair_insertion` is the pre-optimization implementation: it builds
every candidate route and re-measures it with path_length. Keep it here as an
oracle so the O(1)-delta version can never drift from it.
"""
import random
from datetime import datetime, timedelta, timezone

import pytest
from app.optimizer import best_pair_insertion, path_length, route_feasible
from app.schemas import Coordinate, DeliveryCreate, VehicleCreate
from app.state import LogisticsState
from app.worker import dispatch_one


def reference_best_pair_insertion(st, v, pickup, dropoff, now):
    base = v.route
    base_len = path_length(st, v.location, base)
    best = None
    for i in range(len(base) + 1):
        for j in range(i, len(base) + 1):
            cand = base[:i] + [pickup.id] + base[i:j] + [dropoff.id] + base[j:]
            cost = path_length(st, v.location, cand) - base_len
            if best is not None and cost >= best[1]:
                continue
            if route_feasible(st, v, cand, now):
                best = (cand, cost)
    return best


def point(rng):
    return Coordinate(lat=rng.uniform(9.5, 11.0), lng=rng.uniform(76.0, 77.0))


async def build_state(seed: int):
    rng = random.Random(seed)
    now = datetime.now(timezone.utc)
    st = LogisticsState()
    st.balance_km_per_stop = rng.choice([0.0, 2.0])
    for _ in range(5):
        await st.add_vehicle(VehicleCreate(location=point(rng), capacity=8))
    for _ in range(14):
        d = await st.add_delivery(DeliveryCreate(
            pickup=point(rng), dropoff=point(rng), demand=rng.randint(1, 5),
            priority=rng.randint(1, 5),
            expires_at=now + timedelta(hours=rng.uniform(1, 14))))
        await dispatch_one(st, d.id)  # some stay pending; that is fine
    return st, rng, now


@pytest.mark.asyncio
async def test_matches_reference_on_random_states():
    compared = infeasible = 0
    for seed in range(30):
        st, rng, now = await build_state(seed)
        for _ in range(6):
            d = await st.add_delivery(DeliveryCreate(
                pickup=point(rng), dropoff=point(rng), demand=rng.randint(1, 5),
                expires_at=now + timedelta(hours=rng.uniform(1, 14))))
            pu, do = st.stops[d.pickup_stop_id], st.stops[d.dropoff_stop_id]
            for v in st.vehicles.values():
                ref = reference_best_pair_insertion(st, v, pu, do, now)
                new = best_pair_insertion(st, v, pu, do, now)
                if ref is None:
                    infeasible += 1
                    assert new is None
                    continue
                compared += 1
                assert new is not None
                assert new[0] == ref[0]
                assert new[1] == pytest.approx(ref[1], abs=1e-6)
                assert route_feasible(st, v, new[0], now)

                # max_cost is an exact cut-off: nothing cheaper exists, the optimum is found
                assert best_pair_insertion(st, v, pu, do, now, max_cost=ref[1] - 1e-6) is None
                again = best_pair_insertion(st, v, pu, do, now, max_cost=ref[1] + 1e-6)
                assert again is not None and again[0] == ref[0]
    assert compared > 100 and infeasible > 20  # both branches really exercised


@pytest.mark.asyncio
async def test_dispatch_cost_is_extra_km_not_route_length():
    st = LogisticsState()
    st.balance_km_per_stop = 0.0
    v = await st.add_vehicle(VehicleCreate(location=Coordinate(lat=10, lng=76), capacity=10))
    d = await st.add_delivery(DeliveryCreate(
        pickup=Coordinate(lat=10.1, lng=76.1), dropoff=Coordinate(lat=10.2, lng=76.2), demand=2))
    now = datetime.now(timezone.utc)
    route, cost = best_pair_insertion(
        st, v, st.stops[d.pickup_stop_id], st.stops[d.dropoff_stop_id], now)
    assert route == [d.pickup_stop_id, d.dropoff_stop_id]
    assert cost == pytest.approx(path_length(st, v.location, route))
