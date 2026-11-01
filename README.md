# Real-Time Dynamic Route Optimizer

Real-time route optimization for distributed logistics. Vehicles and delivery stops are streamed in, and routes are re-optimized continuously by background workers.

## Background
This project grew out of SustainEats, my K-DISC Young Innovators Programme
idea: a platform connecting restaurants, cafes and grocery stores that have
surplus food with people and organizations in need, with deliveries
coordinated by the app. SustainEats is at concept/prototype stage. This repo
is a standalone engine for its hardest backend problem: dispatching and
re-optimizing deliveries in real time.

## Features
- FastAPI service with Pydantic-validated request and response models
- In-memory state engine with O(1) lookups and a memoized haversine distance matrix
- Capacity-checked, lock-guarded stop assignment
- Cheapest-insertion dispatch plus 2-opt route improvement
- Pickup→dropoff deliveries: donor visited before recipient, on the same vehicle
- Capacity tracked as a load profile along the route (load rises at pickup, falls at dropoff)
- Expiry deadlines checked against an ETA estimate (assumed 30 km/h, no loading time); expired deliveries are marked `failed`
- Load-balanced dispatch: cost = extra km + a per-stop penalty on long routes, scaled by `priority` (urgent items care less about balance)
- Asyncio background worker that drains a pending queue

## Tech Stack
Python 3.14 · FastAPI · Pydantic v2 · asyncio · pytest

## Project Structure
    app/
      schemas.py     # Pydantic models
      state.py       # in-memory state engine
      optimizer.py   # cheapest insertion + 2-opt
      worker.py      # asyncio dispatch worker
      main.py        # FastAPI endpoints
    benchmarks/
      bench.py       # seeded dispatch benchmark (balancing off vs on)
    tests/

## Run Locally
    python -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    pytest -q
    uvicorn app.main:app --reload

Then open `/docs` for the interactive API.

## API
- `POST /vehicles`, `GET /vehicles`, `PUT /vehicles/{id}/location`
- `POST /stops` (returns 202; assignment happens in the background), `GET /stops/{id}`
- `POST /deliveries` (donor pickup + recipient dropoff, optional `expires_at`; returns 202), `GET /deliveries/{id}`
- `GET /routes`, `GET /health`

## Benchmarks
Seeded random workload in a Kerala-sized box: vehicles of capacity 20, deliveries
of demand 1-5, priority 1-5, no expiry. Dispatch only (no HTTP), one delivery at a time
through the same code path as the worker. Single process, CPython, run on a cloud
sandbox, one run per configuration, so treat timings as indicative and expect
different numbers on your machine. Reproduce with
`python -m benchmarks.bench --vehicles 50 --deliveries 300 --seed 42`.

**50 vehicles, 300 deliveries (seed 42)**

| Metric | No balancing | Balancing (2 km/stop) |
|---|---|---|
| Longest route | 3,253 km | 493 km |
| Longest route / mean route | 13.8x | 2.1x |
| Most stops on one vehicle | 164 | 28 |
| Idle vehicles | 39 | 10 |
| Total distance | 11,774 km | 11,503 km |
| Mean / p95 dispatch time | 912 ms / 2,525 ms | 44.6 ms / 104 ms |

**20 vehicles, 100 deliveries, two more seeds**

| Seed | Longest/mean (off → on) | Total distance (off → on) | Mean dispatch (off → on) |
|---|---|---|---|
| 1 | 8.4x → 2.0x | 4,138 → 4,539 km (+9.7%) | 117 → 10.6 ms |
| 2 | 8.4x → 2.5x | 3,722 → 3,909 km (+5.0%) | 98 → 12.8 ms |

Takeaways and limits:
- Pure cheapest insertion piles most work on a few vehicles. Balancing fixes the skew,
  and costs 5-10% extra total distance in two of the three runs (it was 2% lower in the third).
- Dispatch is much faster with balancing, because pair insertion is roughly O(n³) in
  route length per vehicle (n² slot pairs, each with an O(n) feasibility check), and balancing keeps routes short.
- Still open: 10 of 50 vehicles stay idle at 300 deliveries (the 2 km/stop weight is hand-picked, not tuned),
  and 1,000+ deliveries was not benchmarked because long routes get slow.
- `priority` only scales the balance penalty; it does not reorder the queue.
  Its behavior is unit-tested but its effect is not benchmarked.

## Roadmap
- [x] Data models and state engine
- [x] Cheapest-insertion + 2-opt optimizer, asyncio dispatch worker
- [x] REST API
- [x] Pickup→dropoff pairing (donor before recipient, same vehicle)
- [x] Expiry deadlines (ETA-based feasibility)
- [x] Load balancing across vehicles
- [x] Priority-scaled dispatch cost
- [x] Benchmarks
- [ ] Faster pair insertion (avoid O(n³) per vehicle) and 1,000+ delivery benchmark
- [ ] Tune the balance weight; priority-ordered queue
- [ ] Redis-backed state for horizontal scaling

## License
MIT