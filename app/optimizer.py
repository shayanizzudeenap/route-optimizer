from __future__ import annotations

import heapq
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
    st: LogisticsState,
    v: Vehicle,
    pickup: Stop,
    dropoff: Stop,
    now: datetime,
    max_cost: float = float("inf"),
) -> tuple[list[str], float] | None:
    """Cheapest feasible (pickup slot, dropoff slot) with dropoff after pickup.
    Returns (new_route, extra_km), or None if no feasible slot costs < max_cost.

    The extra distance of every slot pair is computed in O(1) from per-slot
    insertion costs, so ranking all O(n^2) pairs costs O(n^2) arithmetic. The
    O(n) feasibility check then runs lazily in ascending cost order and stops at
    the first feasible pair (ties resolve to the lowest (i, j), as before)."""
    base = v.route
    n = len(base)
    dist = st.distance
    pts = [v.location] + [st.stops[sid].location for sid in base]
    p, d = pickup.location, dropoff.location
    pd = dist(p, d)

    # Each distance is looked up once: to the pickup, to the dropoff, and along the
    # existing route's edges.
    dp = [dist(pt, p) for pt in pts]
    dd = [dist(pt, d) for pt in pts]
    edge = [dist(pts[i], pts[i + 1]) for i in range(n)]

    # ins_p[i] / ins_d[i]: extra km of placing that stop alone between pts[i], pts[i+1].
    # The open path has no edge after the last stop, so appending costs just dp / dd.
    ins_p = [dp[i] + dp[i + 1] - edge[i] for i in range(n)] + [dp[n]]
    ins_d = [dd[i] + dd[i + 1] - edge[i] for i in range(n)] + [dd[n]]

    cands: list[tuple[float, int, int]] = []
    for i in range(n + 1):
        # pickup and dropoff adjacent in the same slot: pts[i] -> p -> d -> pts[i+1]
        c = dp[i] + pd + (dd[i + 1] - edge[i] if i < n else 0.0)
        if c < max_cost:
            cands.append((c, i, i))
        ip = ins_p[i]
        if ip >= max_cost:  # dropoff insertion cost is >= 0 (triangle inequality)
            continue
        for j in range(i + 1, n + 1):
            c = ip + ins_d[j]
            if c < max_cost:
                cands.append((c, i, j))

    heapq.heapify(cands)
    while cands:
        c, i, j = heapq.heappop(cands)
        route = base[:i] + [pickup.id] + base[i:j] + [dropoff.id] + base[j:]
        if route_feasible(st, v, route, now):
            return route, c
    return None


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
