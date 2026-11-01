from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Callable

from app.schemas import Coordinate, Stop, StopKind, Vehicle

if TYPE_CHECKING:
    from app.state import LogisticsState

SPEED_KMH = 30.0  # assumed average vehicle speed


def as_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def path_length(st: LogisticsState, start: Coordinate, ids: list[str]) -> float:
    """Open-path length: vehicle position -> stops in order (no return leg)."""
    total, prev = 0.0, start
    for sid in ids:
        loc = st.stops[sid].location
        total += st.distance(prev, loc)
        prev = loc
    return total


def route_feasible(st: LogisticsState, v: Vehicle, ids: list[str], now: datetime) -> bool:
    """Checks capacity along the route, pickup-before-dropoff, and deadlines (ETA)."""
    load, t, prev = 0, now, v.location
    picked: set[str] = set()
    for sid in ids:
        s = st.stops[sid]
        t += timedelta(hours=st.distance(prev, s.location) / SPEED_KMH)
        prev = s.location
        if s.kind is StopKind.DROPOFF:
            if st.deliveries[s.delivery_id].pickup_stop_id not in picked:
                return False
            load -= s.demand
        else:
            load += s.demand
            picked.add(sid)
        if load > v.capacity:
            return False
        if s.deadline is not None and t > as_utc(s.deadline):
            return False
    return True


def cheapest_insertion(st: LogisticsState, v: Vehicle, stop: Stop) -> tuple[int, float]:
    """Best slot in v.route for `stop`. Returns (index, extra_km). O(n)."""
    best_i, best_delta = 0, float("inf")
    prev = v.location
    n = len(v.route)
    for i in range(n + 1):
        nxt = st.stops[v.route[i]].location if i < n else None
        delta = st.distance(prev, stop.location)
        if nxt is not None:
            delta += st.distance(stop.location, nxt) - st.distance(prev, nxt)
        if delta < best_delta:
            best_i, best_delta = i, delta
        if nxt is not None:
            prev = nxt
    return best_i, best_delta


def best_pair_insertion(
    st: LogisticsState, v: Vehicle, pickup: Stop, dropoff: Stop, now: datetime
) -> tuple[list[str], float] | None:
    """Try every (pickup slot, dropoff slot) with dropoff after pickup.
    Returns (new_route, extra_km) for the cheapest feasible one, else None."""
    base = v.route
    base_len = path_length(st, v.location, base)
    best: tuple[list[str], float] | None = None
    for i in range(len(base) + 1):
        for j in range(i, len(base) + 1):
            cand = base[:i] + [pickup.id] + base[i:j] + [dropoff.id] + base[j:]
            cost = path_length(st, v.location, cand) - base_len
            if best is not None and cost >= best[1]:
                continue
            if route_feasible(st, v, cand, now):
                best = (cand, cost)
    return best


def two_opt(
    st: LogisticsState,
    start: Coordinate,
    ids: list[str],
    feasible: Callable[[list[str]], bool] | None = None,
) -> list[str]:
    """2-opt on an open path with fixed start. A reversal is applied only if it
    shortens the route AND `feasible(candidate)` holds (keeps precedence/deadlines)."""
    route = ids[:]
    n = len(route)
    improved = True
    while improved:
        improved = False
        for i in range(n - 1):
            for j in range(i + 1, n):
                a = start if i == 0 else st.stops[route[i - 1]].location
                b = st.stops[route[i]].location
                c = st.stops[route[j]].location
                d = st.stops[route[j + 1]].location if j + 1 < n else None
                old = st.distance(a, b) + (st.distance(c, d) if d else 0.0)
                new = st.distance(a, c) + (st.distance(b, d) if d else 0.0)
                if new < old - 1e-9:
                    cand = route[:i] + route[i : j + 1][::-1] + route[j + 1 :]
                    if feasible is None or feasible(cand):
                        route = cand
                        improved = True
    return route
