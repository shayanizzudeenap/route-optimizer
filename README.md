# Real-Time Dynamic Route Optimizer

Real-time route optimization for distributed logistics. Vehicles and delivery stops are streamed in, and routes are re-optimized continuously by background workers.

## Features
- FastAPI service with Pydantic-validated request and response models
- In-memory state engine with O(1) lookups and a memoized haversine distance matrix
- Capacity-checked, lock-guarded stop assignment
- Asyncio background worker that drains a pending-stop queue

## Tech Stack
Python 3.14 · FastAPI · Pydantic v2 · asyncio · pytest

## Project Structure
    app/
      schemas.py   # Pydantic models
      state.py     # in-memory state engine
    tests/

## Run Locally
    python -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    pytest -q

## Roadmap
- [x] Data models and state engine
- [ ] Route optimizer (nearest-neighbor insertion + 2-opt)
- [ ] Background re-optimization worker
- [ ] REST API endpoints
- [ ] Benchmarks
- [ ] Redis-backed state for horizontal scaling

## License
MIT