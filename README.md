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

## Roadmap
- [x] Data models and state engine
- [x] Cheapest-insertion + 2-opt optimizer, asyncio dispatch worker
- [x] REST API
- [x] Pickup→dropoff pairing (donor before recipient, same vehicle)
- [x] Expiry deadlines (ETA-based feasibility)
- [ ] Urgency-weighted dispatch (`priority` is stored but not yet used in the cost)
- [ ] Load balancing across vehicles
- [ ] Benchmarks
- [ ] Redis-backed state for horizontal scaling

## License
MIT