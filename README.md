# Mosaic Core

A constraint-governed AI tile runtime: deterministic, composable "tiles" (semantic router, route dispatch, sentiment, pressure telemetry, proof evaluator, guided hallucinator, and more) orchestrated by a multi-hop resolver, with JSON-first governance documentation, an automated benchmarking pipeline, and a local TinyLLaMA integration.

## Key Ideas

The system is built around four immutable architectural invariants:

- **I1 — Function determinism**: identical inputs produce identical outputs; no randomness or timestamps in core logic.
- **I2 — Memory isolation**: explicit memory tracking with cleanup contracts; all allocations bounded.
- **I3 — Workspace coherence**: directory structure and schemas match `core_reference.json`.
- **I4 — Documentation purity**: JSON-first docs for AI agents, derived markdown for humans.

Every component ships with compliance metadata, coverage numbers, and proof artifacts, tracked in `ai_docs/component_index.json` and the `knowledge_base/`.

## Repository Layout

| Path | Purpose |
| --- | --- |
| `core_reference.json` | Architectural foundation: schemas, invariants, error registry |
| `behavioral_directives.json` | Behavioral protocols for AI agents working in the repo |
| `src/runtime/` | Tile runtime: resolver, tiles, benchmarking runner, dashboard services |
| `src/main.py` | CLI entry point with deterministic demos (`--demo sentiment`, `--demo imagination`) |
| `tests/` | Pytest suite covering tiles, resolver, schemas, and governance sync |
| `ai_docs/` | JSON-first governance docs: contracts, protocols, dashboards, component index |
| `knowledge_base/` | Techniques, innovations, automation patterns, and session history |
| `logs/` | Coverage snapshots and benchmark evidence bundles |
| `ui/benchmark_dashboard/` | Vite/TypeScript dashboard for benchmark results |
| `scripts/` | Helper scripts (e.g. local TinyLLaMA server startup) |

## Getting Started

```bash
# create environment and install test deps
python -m venv .venv && source .venv/bin/activate
pip install pytest

# run the test suite
python -m pytest

# run a deterministic demo
python -m src.main --demo sentiment
```

### Benchmarking

```bash
# execute a benchmark playlist and regenerate the dashboard JSON
python -m runtime.benchmarking_runner --playlist playlist.phase3_regression

# sync dashboard digest into SYSTEM_STATUS.md
python -m runtime.benchmark_dashboard_cli --update-system-status
```

### Local model (optional)

Some scenarios use a local TinyLLaMA served via llama.cpp. Model weights are not included in this repo; place a GGUF model under `models/` and start it with:

```bash
scripts/start_tinyllama_server.sh
```

### Dashboard UI

```bash
cd ui/benchmark_dashboard
npm install
npm run dev
```

## Status

See [SYSTEM_STATUS.md](SYSTEM_STATUS.md) and [SYSTEM_SUMMARY.md](SYSTEM_SUMMARY.md) for current component health, coverage, and benchmarking digests.

## License

[MIT](LICENSE)
