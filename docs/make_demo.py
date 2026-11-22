"""Render docs/demo.png: the dispatcher's routes for a small seeded workload.

Runs the real dispatch code (no HTTP), then draws each vehicle's route.
Requires matplotlib, which is not a runtime dependency:

    pip install matplotlib
    python docs/make_demo.py
"""
from __future__ import annotations

import asyncio
import random
import string
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.optimizer import path_length  # noqa: E402
from app.schemas import Coordinate, DeliveryCreate, StopKind, VehicleCreate  # noqa: E402
from app.state import LogisticsState  # noqa: E402
from app.worker import dispatch_one  # noqa: E402

SEED, N_VEHICLES, N_DELIVERIES = 1, 4, 10
LAT, LNG = (9.90, 10.10), (76.20, 76.40)  # city-sized box, roughly 22 km square
COLORS = ["#0072B2", "#D55E00", "#009E73", "#CC79A7"]  # colour-blind-safe (Okabe-Ito)


def point(rng: random.Random) -> Coordinate:
    return Coordinate(lat=rng.uniform(*LAT), lng=rng.uniform(*LNG))


async def build() -> tuple[LogisticsState, dict[str, str]]:
    rng = random.Random(SEED)
    st = LogisticsState()
    for _ in range(N_VEHICLES):
        await st.add_vehicle(VehicleCreate(location=point(rng), capacity=10))
    letters: dict[str, str] = {}  # delivery id -> letter
    for i in range(N_DELIVERIES):
        d = await st.add_delivery(DeliveryCreate(
            pickup=point(rng), dropoff=point(rng), demand=rng.randint(1, 4)))
        letters[d.id] = string.ascii_uppercase[i]
        await dispatch_one(st, d.id)
    return st, letters


def draw(st: LogisticsState, letters: dict[str, str], out: Path) -> None:
    fig, ax = plt.subplots(figsize=(9, 7.5), dpi=150)
    total = 0.0
    for n, (color, v) in enumerate(zip(COLORS, st.vehicles.values()), start=1):
        pts = [v.location] + [st.stops[sid].location for sid in v.route]
        km = path_length(st, v.location, v.route)
        total += km
        xs, ys = [p.lng for p in pts], [p.lat for p in pts]
        for k in range(len(pts) - 1):  # arrows show visit order
            ax.annotate("", xy=(xs[k + 1], ys[k + 1]), xytext=(xs[k], ys[k]),
                        arrowprops=dict(arrowstyle="-|>", color=color, lw=1.8,
                                        shrinkA=6, shrinkB=7), zorder=2)
        ax.scatter([xs[0]], [ys[0]], marker="*", s=330, color=color,
                   edgecolor="black", linewidth=0.8, zorder=4,
                   label=f"Vehicle {n} (start): {len(v.route)} stops, {km:.0f} km")
        for sid in v.route:
            s = st.stops[sid]
            is_pickup = s.kind is StopKind.PICKUP
            ax.scatter([s.location.lng], [s.location.lat], s=95, zorder=3,
                       marker="o" if is_pickup else "s",
                       color=color if is_pickup else "white",
                       edgecolor=color, linewidth=2)
            ax.annotate(letters[s.delivery_id], (s.location.lng, s.location.lat),
                        textcoords="offset points", xytext=(7, 7), fontsize=10,
                        fontweight="bold")
    ax.scatter([], [], marker="o", color="#555555", label="Pickup (donor)")
    ax.scatter([], [], marker="s", color="white", edgecolor="#555555",
               linewidth=2, label="Dropoff (recipient)")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_title(f"Dispatcher output: {N_DELIVERIES} deliveries, {N_VEHICLES} vehicles "
                 f"(seed {SEED}), {total:.0f} km total", fontsize=12)
    ax.grid(alpha=0.25)
    ax.margins(0.06)
    # Legend sits below the axes so it never hides a stop.
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=2,
              fontsize=9, frameon=False)
    fig.tight_layout()
    fig.savefig(out)


if __name__ == "__main__":
    state, letters = asyncio.run(build())
    unplaced = [letters[d.id] for d in state.deliveries.values() if d.vehicle_id is None]
    if unplaced:
        print("warning: unplaced deliveries:", unplaced)
    out = Path(__file__).with_name("demo.png")
    draw(state, letters, out)
    print("wrote", out)
