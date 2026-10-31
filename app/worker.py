from __future__ import annotations

import asyncio
import logging

from app.optimizer import cheapest_insertion, two_opt
from app.schemas import StopStatus, VehicleStatus
from app.state import LogisticsState

log = logging.getLogger("worker")
RETRY_SECONDS = 2.0


async def dispatch_one(st: LogisticsState, stop_id: str) -> bool:
    """Assign one stop to the vehicle with the lowest insertion cost,
    then re-run 2-opt on that route. Returns False if no vehicle fits."""
    async with st.lock:
        stop = st.stops.get(stop_id)
        if stop is None or stop.status is not StopStatus.PENDING:
            return True  # nothing to do

        best = None  # (extra_km, vehicle, index)
        for v in st.vehicles.values():
            if v.status is VehicleStatus.OFFLINE or v.load + stop.demand > v.capacity:
                continue
            idx, delta = cheapest_insertion(st, v, stop)
            if best is None or delta < best[0]:
                best = (delta, v, idx)

        if best is None:
            return False

        _, v, idx = best
        st.assign_locked(stop_id, v.id, idx)
        v.route = two_opt(st, v.location, v.route)
        return True


async def run_worker(st: LogisticsState) -> None:
    """Background loop: drain st.pending forever."""
    loop = asyncio.get_running_loop()
    while True:
        stop_id = await st.pending.get()
        try:
            if not await dispatch_one(st, stop_id):
                # no capacity right now: retry later without blocking the queue
                loop.call_later(RETRY_SECONDS, st.pending.put_nowait, stop_id)
        except Exception:
            log.exception("dispatch failed for stop %s", stop_id)
        finally:
            st.pending.task_done()