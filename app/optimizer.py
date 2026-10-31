from __future__ import annotations

from typing import TYPE_CHECKING

from app.schemas import Coordinate, Stop, Vehicle

if TYPE_CHECKING:
    from app.state import LogisticsState


def path_length(st: LogisticsState, start: Coordinate, ids: list[str]) -> float:
    """Open-path length: vehicle position -> stops in order (no return leg)."""
    total, prev = 0.0, start
    for sid in ids:
        loc = st.stops[sid].location
        total += st.distance(prev, loc)
        prev = loc
    return total


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


def two_opt(st: LogisticsState, start: Coordinate, ids: list[str]) -> list[str]:
    """2-opt local search on an open path with a fixed start. O(n^2) per pass."""
    route = ids[:]
    n = len(route)
    loc = lambda k: st.stops[route[k]].location  # noqa: E731
    improved = True
    while improved:
        improved = False
        for i in range(n - 1):
            a = start if i == 0 else loc(i - 1)
            b = loc(i)
            for j in range(i + 1, n):
                c = loc(j)
                d = loc(j + 1) if j + 1 < n else None
                old = st.distance(a, b) + (st.distance(c, d) if d else 0.0)
                new = st.distance(a, c) + (st.distance(b, d) if d else 0.0)
                if new < old - 1e-9:
                    route[i : j + 1] = reversed(route[i : j + 1])
                    b = loc(i)  # segment reversed, refresh b
                    improved = True
    return route