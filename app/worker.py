from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from app.optimizer import (
    as_utc, best_pair_insertion, cheapest_insertion, route_feasible, two_opt,
)
from app.schemas import StopStatus, VehicleStatus
from app.state import LogisticsState

log = logging.getLogger("worker")
RETRY_SECONDS = 2.0


def _dispatch_delivery_locked(st: LogisticsState, delivery_id: str, now: datetime) -> bool:
    d = st.deliveries.get(delivery_id)
    if d is None or d.status is not StopStatus.PENDING:
        return True
    if d.expires_at is not None and as_utc(d.expires_at) <= now:
        st.fail_delivery_locked(d)  # food expired before we could place it
        return True

    pu, do = st.stops[d.pickup_stop_id], st.stops[d.dropoff_stop_id]
    best = None  # (extra_km, vehicle, route)
    for v in st.vehicles.values():
        if v.status is VehicleStatus.OFFLINE:
            continue
        res = best_pair_insertion(st, v, pu, do, now)
        if res and (best is None or res[1] < best[0]):
            best = (res[1], v, res[0])
    if best is None:
        return False  # nothing feasible right now; worker retries

    _, v, route = best
    st.assign_pair_locked(d, v.id, route)
    v.route = two_opt(st, v.location, v.route,
                      feasible=lambda r: route_feasible(st, v, r, now))
    return True


async def dispatch_one(st: LogisticsState, item_id: str) -> bool:
    """Dispatch a stop or a delivery. Returns False if it can't be placed yet."""
    now = datetime.now(timezone.utc)
    async with st.lock:
        if item_id in st.deliveries:
            return _dispatch_delivery_locked(st, item_id, now)

        stop = st.stops.get(item_id)
        if stop is None or stop.status is not StopStatus.PENDING:
            return True

        best = None  # (extra_km, vehicle, index)
        for v in st.vehicles.values():
            if v.status is VehicleStatus.OFFLINE or v.load + stop.demand > v.capacity:
                continue
            idx, delta = cheapest_insertion(st, v, stop)
            cand = v.route[:idx] + [stop.id] + v.route[idx:]
            if not route_feasible(st, v, cand, now):
                continue
            if best is None or delta < best[0]:
                best = (delta, v, idx)
        if best is None:
            return False

        _, v, idx = best
        st.assign_locked(item_id, v.id, idx)
        v.route = two_opt(st, v.location, v.route,
                          feasible=lambda r: route_feasible(st, v, r, now))
        return True


async def run_worker(st: LogisticsState) -> None:
    """Background loop: drain st.pending forever."""
    loop = asyncio.get_running_loop()
    while True:
        item_id = await st.pending.get()
        try:
            if not await dispatch_one(st, item_id):
                loop.call_later(RETRY_SECONDS, st.pending.put_nowait, item_id)
        except Exception:
            log.exception("dispatch failed for %s", item_id)
        finally:
            st.pending.task_done()
