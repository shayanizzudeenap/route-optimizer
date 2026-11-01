"""Benchmark the dispatcher: balancing off vs on, same seeded workload.

Usage (from the repo root):
    python -m benchmarks.bench --vehicles 50 --deliveries 300
    python -m benchmarks.bench --vehicles 20 --deliveries 100 --seed 7

Measures dispatch only (no HTTP). Each delivery is dispatched one at a time
through the same code path the background worker uses.
"""
from __future__ import annotations

import argparse
import asyncio
import random
import statistics
import time

from app.optimizer import path_length
from app.schemas import Coordinate, DeliveryCreate, StopStatus, VehicleCreate
from app.state import LogisticsState
from app.worker import dispatch_one

# Rough Kerala bounding box.
LAT = (9.5, 11.0)
LNG = (76.0, 77.0)


def rand_point(rng: random.Random) -> Coordinate:
    return Coordinate(lat=rng.uniform(*LAT), lng=rng.uniform(*LNG))


async def run_once(n_vehicles: int, n_deliveries: int, seed: int, balance: float) -> dict:
    rng = random.Random(seed)
    st = LogisticsState()
    st.balance_km_per_stop = balance

    for _ in range(n_vehicles):
        await st.add_vehicle(VehicleCreate(location=rand_point(rng), capacity=20))

    ids = []
    for _ in range(n_deliveries):
        d = await st.add_delivery(DeliveryCreate(
            pickup=rand_point(rng), dropoff=rand_point(rng),
            demand=rng.randint(1, 5), priority=rng.randint(1, 5)))
        ids.append(d.id)

    per_call_ms: list[float] = []
    t0 = time.perf_counter()
    for did in ids:
        t = time.perf_counter()
        await dispatch_one(st, did)
        per_call_ms.append((time.perf_counter() - t) * 1000)
    total_s = time.perf_counter() - t0

    lengths = [path_length(st, v.location, v.route) for v in st.vehicles.values()]
    stops_per_vehicle = [len(v.route) for v in st.vehicles.values()]
    assigned = sum(1 for d in st.deliveries.values() if d.status is StopStatus.ASSIGNED)
    per_call_ms.sort()
    mean_len = statistics.mean(lengths)

    return {
        "balance_km_per_stop": balance,
        "assigned": assigned,
        "unplaced": n_deliveries - assigned,
        "total_km": sum(lengths),
        "mean_route_km": mean_len,
        "max_route_km": max(lengths),
        "max_over_mean": max(lengths) / mean_len if mean_len else 0.0,
        "max_stops": max(stops_per_vehicle),
        "idle_vehicles": sum(1 for n in stops_per_vehicle if n == 0),
        "total_s": total_s,
        "mean_ms": statistics.mean(per_call_ms),
        "p95_ms": per_call_ms[int(0.95 * (len(per_call_ms) - 1))],
        "max_ms": per_call_ms[-1],
    }


def fmt_table(rows: list[dict]) -> str:
    keys = [
        ("assigned", "{:d}"), ("unplaced", "{:d}"), ("total_km", "{:,.0f}"),
        ("mean_route_km", "{:,.0f}"), ("max_route_km", "{:,.0f}"),
        ("max_over_mean", "{:.2f}"), ("max_stops", "{:d}"), ("idle_vehicles", "{:d}"),
        ("total_s", "{:.2f}"), ("mean_ms", "{:.1f}"), ("p95_ms", "{:.1f}"), ("max_ms", "{:.1f}"),
    ]
    head = f"{'metric':<16}" + "".join(f"{'balance=' + str(r['balance_km_per_stop']):>16}" for r in rows)
    lines = [head, "-" * len(head)]
    for k, f in keys:
        lines.append(f"{k:<16}" + "".join(f"{f.format(r[k]):>16}" for r in rows))
    return "\n".join(lines)


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--vehicles", type=int, default=50)
    p.add_argument("--deliveries", type=int, default=300)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--balance", type=float, default=2.0, help="km penalty per route stop")
    a = p.parse_args()

    print(f"vehicles={a.vehicles} deliveries={a.deliveries} seed={a.seed} (capacity 20, demand 1-5)\n")
    rows = [
        await run_once(a.vehicles, a.deliveries, a.seed, 0.0),
        await run_once(a.vehicles, a.deliveries, a.seed, a.balance),
    ]
    print(fmt_table(rows))


if __name__ == "__main__":
    asyncio.run(main())
