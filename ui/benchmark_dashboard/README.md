# Benchmark Dashboard UI

Lightweight React + Vite client for the benchmarking service exposed by `runtime/benchmark_dashboard_service.py`.

## Prerequisites

- Node 18+
- Benchmark dashboard service running locally (e.g. `PYTHONPATH=src python -m runtime.benchmark_dashboard_service --host 127.0.0.1 --port 8080`).

## Setup

```bash
cd ui/benchmark_dashboard
npm install
```

## Development

```bash
npm run dev
```

Vite proxies `/api` and `/healthz` requests to `http://127.0.0.1:8080`, so the UI automatically reads live dashboard data.

## Build

```bash
npm run build
```

Artifacts land in `dist/` and can be served by any static file server (e.g. `npm run preview`).
