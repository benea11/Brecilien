# Brécilien — DECT NR+ Link Simulator

Physics-grounded propagation/PHY/HARQ simulator for DECT NR+ outdoor mesh
deployments. The app has two parts:

- `backend/` — FastAPI service (Python 3.11) serving the simulation/planning API on port `8000`.
- `frontend/` — React + TypeScript + Vite app on port `5173`.

## Prerequisites

- Python 3.11
- Node.js (with npm)

## 1. Start the backend

```bash
cd backend
source .venv/bin/activate   # a .venv already exists; if missing, create with: python3.11 -m venv .venv
pip install -e ".[dev]"     # only needed the first time / after dependency changes
uvicorn app.main:app --reload
```

The API will be available at `http://localhost:8000`.

## 2. Start the frontend

In a separate terminal:

```bash
cd frontend
npm install                 # only needed the first time / after dependency changes
VITE_API_BASE=http://127.0.0.1:8000 npm run dev -- --host 127.0.0.1
```

The app will be available at `http://localhost:5173`.

## Notes

- The backend must be running before the frontend can load projects, buildings,
  or run simulations — the frontend talks to it at `http://localhost:8000`
  by default (override with a `VITE_API_BASE` env var if needed).
- CORS on the backend is currently locked to `http://localhost:5173` /
  `http://127.0.0.1:5173`, so serve the frontend from one of those origins.

## Running tests (backend)

```bash
cd backend
source .venv/bin/activate
pytest
```
