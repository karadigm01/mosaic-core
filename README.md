# Mosaic Core

A deterministic AI "tile" runtime that composes small, contract-bound capability modules (routing, dispatch, sentiment, pressure telemetry, proof evaluation, guided text generation) into multi-hop resolution chains, and emits a machine-checkable proof record for every run.

Instead of one opaque model call, Mosaic Core resolves a goal by planning a chain of independent tiles, executing each under an explicit resource budget, and recording the full lineage — tile sequence, capability bindings, per-hop work metrics, pressure/alert state, and presentation views — as a single JSON proof. The runtime core is dependency-free Python governed by four architectural invariants (determinism, memory isolation, workspace coherence, JSON-first documentation), with an optional local TinyLLaMA integration for one generative tile.

## Project Status

| Field              | Value |
| ------------------ | ----- |
| Project type       | Research prototype (constraint-governed runtime) |
| Maturity           | Working Prototype |
| Primary language   | Python 3.12 (stdlib-only runtime; pytest for tests) |
| Deterministic core | Partial — tile/resolver core is deterministic; the optional TinyLLaMA tile depends on a local LLM |
| Primary validation | Test suite (105 passed, 1 skipped without the optional local model, verified 2026-07-25) plus checked-in benchmark evidence bundles |
| License            | MIT ([LICENSE](LICENSE)) |

Test counts above come from a test run performed during this README revision. Coverage and benchmark figures cited below come from dated, checked-in artifacts.

## Purpose

The system explores one central question:

> Can useful AI behavior be assembled from small, independently contracted, deterministic modules — so that every result carries a complete, replayable proof of how it was produced and what resources it consumed?

Conventional pipelines make it hard to answer "which component produced this, under what budget, and would the same input give the same output?" Mosaic Core makes those properties structural: tiles declare input/output types and resource budgets up front, the resolver plans and executes chains against those contracts, and every resolution produces an auditable proof record rather than a bare answer.

## Core Capabilities

- **Deterministic multi-hop resolution:** A resolver plans a capability chain (e.g. semantic routing → dispatch → pressure summary) from registered tile contracts and executes it hop by hop, producing identical outputs for identical inputs in the core path.
- **Proof-record generation:** Every resolution emits a structured proof containing the tile sequence, capability bindings, per-hop work metrics, chain-quality facts, and presentation-ready views.
- **Pressure telemetry and alerting:** Each hop's work metrics are compared against the tile's declared budget; over-budget hops generate severity-classified pressure signals and alert-panel views inside the proof.
- **Guarded local-LLM generation:** An optional guided-hallucinator tile calls a local TinyLLaMA (llama.cpp) server with health probing, slot-contention tracking, and structured rejection when the server is unavailable — the runtime never crashes on a missing model.
- **Benchmarking with evidence capture:** A scenario/playlist runner executes catalogued demos, records per-scenario evidence bundles (proofs, telemetry, diffs) under `logs/benchmarks/`, and regenerates a dashboard JSON consumed by a React UI.
- **Governance synchronization:** Automation tooling syncs test coverage into a machine-readable component index (`ai_docs/component_index.json`) and rewrites status markdown from JSON, keeping human docs derived from machine docs; a CI workflow fails when governance artifacts drift.

## How It Works

```text
input fact (JSON payload in constraint substrate)
→ goal (desired output type + invariant constraints)
→ resolver plans capability chain from tile contracts
→ deterministic tile execution, hop by hop
→ per-hop work metrics vs. declared budgets (pressure signals, alerts)
→ proof record (tile sequence, bindings, telemetry, views)
→ optional: benchmark evidence bundle + dashboard JSON
```

| Layer | Responsibility |
| ----- | -------------- |
| `src/runtime/constraint_substrate.py` | Fact store with TTL, provenance, and invariant-compliance tags; defines `ProofRecord` |
| `src/runtime/tile_registry.py` | Tile contracts: capabilities, input/output types, resource budgets |
| `src/runtime/resolver.py` | Multi-hop planning and execution, pressure computation, proof assembly |
| `src/runtime/*_tile.py` | Individual tiles: semantic router, route dispatch, sentiment, pressure summary/historian, alert panel, proof evaluator, guided hallucinator |
| `src/runtime/benchmarking_runner.py` | Scenario/playlist execution and evidence capture |
| `src/runtime/automation_runner.py`, `component_coverage_sync.py` | Coverage sync into the component index; CI drift checks |
| `src/main.py` | CLI demos exercising the resolver end to end |
| `ui/benchmark_dashboard/` | React/Vite dashboard rendering the benchmark JSON |

Governance rules live in `core_reference.json` (invariants I1–I4, quality contracts, error registry) and `behavioral_directives.json`; component health is tracked in `ai_docs/component_index.json` (19 registered components).

## Evidence

| Claim | Evidence | Reproduce or inspect |
| ----- | -------- | -------------------- |
| The tile/resolver core resolves multi-hop chains and emits complete proofs | Test suite: 105 passed, 1 skipped during this revision | `python -m pytest tests/` |
| The sentiment demo chain runs deterministically without any model or network | Reproduced during this revision | `PYTHONPATH=src python -m src.main --demo sentiment` |
| The guided-hallucinator path works end to end against a local TinyLLaMA server, and degrades to a structured rejection without one | Reproduced during this revision (both with and without the server) | `PYTHONPATH=src python -m src.main --demo imagination --prompt "a city made of glass"` |
| Benchmark playlists execute 3/3 scenarios with zero failures | Checked-in evidence bundles dated 2026-01-25 | `logs/benchmarks/playlist.playlist.phase3_regression-20260125T062749Z.json` |
| Runtime coverage is tracked per component (e.g. resolver 97.03 %, sentiment 98.04 %, proof evaluator 100 %) | Component index regenerated by the coverage-sync workflow during this revision (2026-07-25) | `ai_docs/component_index.json`, `logs/coverage-*.json` |
| Governance artifacts are kept in sync and drift fails CI | CI workflow runs the automation runner with coverage sync and rejects uncommitted governance diffs | `.github/workflows/automation-runner.yml` |

### Current Results

| Metric | Result | Source |
| ------ | -----: | ------ |
| Tests (with local TinyLLaMA running) | `106 passed` | Test run during this revision (2026-07-25) |
| Tests (without local model) | `105 passed, 1 skipped` | Test run during this revision (2026-07-25) |
| Registered components healthy | `19/19` | `ai_docs/component_index.json` (regenerated 2026-07-25) |
| Phase 3 regression playlist | `3/3 scenarios, 0 failures` | `logs/benchmarks/` artifact (2026-01-25) |
| Coverage snapshot (all runtime modules) | `85.14 %` | `logs/coverage-20260725T204434.json` (generated during this revision) |

The repository includes benchmark latency evidence (playlist latency span 41 ms in the stored Phase 3 run) but no formal comparative performance benchmark.

## Quick Start

Requires Python 3.10+ (CI uses 3.12). The runtime itself has no third-party dependencies; only pytest is needed for tests.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install pytest

# run the test suite
python -m pytest tests/

# run the deterministic demo (no model or network required)
PYTHONPATH=src python -m src.main --demo sentiment
```

The demo prints a JSON proof record for a three-hop chain (semantic router → route dispatch → pressure summary).

## Usage

### Run the CLI demos

```bash
# deterministic sentiment/pressure chain
PYTHONPATH=src python -m src.main --demo sentiment

# guided-hallucination chain (requires the local TinyLLaMA server, below)
PYTHONPATH=src python -m src.main --demo imagination --prompt "a city made of glass"
```

Without the TinyLLaMA server, the imagination demo returns a structured rejection (`{"status": "rejected", "error_code": "resolver_error", ...}`) rather than crashing.

### Run a benchmark playlist

```bash
# execute a playlist and regenerate ai_docs/benchmarking_dashboard.json
PYTHONPATH=src python -m runtime.benchmarking_runner --playlist playlist.phase3_regression

# or a single scenario
PYTHONPATH=src python -m runtime.benchmarking_runner --scenario scenario.sentiment_chain
```

Scenario and playlist identifiers are catalogued in `ai_docs/benchmarking_scenarios.json` and `ai_docs/benchmarking_playlists.json`. Each run writes evidence bundles to `logs/benchmarks/`.

```bash
# sync the dashboard digest into SYSTEM_SUMMARY.md
PYTHONPATH=src python -m runtime.benchmark_dashboard_cli --update-system-summary
```

### Sync governance coverage (what CI runs)

```bash
PYTHONPATH=src python -m runtime.automation_runner --pattern-id auto-0003 --enable-coverage-sync
```

This runs pytest with coverage and updates `ai_docs/component_index.json`; CI fails if the committed index drifts from the regenerated one.

### Start the local TinyLLaMA server (optional)

Model weights and the llama.cpp build are **not** included in the repository. To enable the generative tile:

1. Build [llama.cpp](https://github.com/ggml-org/llama.cpp) under `models/llama.cpp/` (so that `models/llama.cpp/build/bin/llama-server` exists).
2. Place a TinyLLaMA GGUF file at `models/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf`.
3. Start the server:

```bash
scripts/start_tinyllama_server.sh
```

The server listens on `127.0.0.1:8088` by default (configurable via `LLAMA_SERVER_HOST` / `LLAMA_SERVER_PORT`; the health probe honors `TINYLLAMA_HEALTH_URL`). One integration test is skipped automatically when the server is unreachable.

### Launch the benchmark dashboard UI

```bash
cd ui/benchmark_dashboard
npm install
npm run dev
```

## Example

Input: a single fact `{"text": "I hate waiting for support"}` and the goal `demo.sentiment` requesting a `pressure.summary` output under invariants I1–I4.

Output (excerpt of the actual proof record printed by `--demo sentiment`):

```json
{
  "proof_id": "proof::demo.sentiment::tile.reasoning.pressure_summary",
  "tile_sequence": [
    "tile.lang.semantic_router",
    "tile.reasoning.route_dispatch",
    "tile.reasoning.pressure_summary"
  ],
  "chain_quality": {
    "alert_count": 0.0,
    "hop_count": 3.0,
    "pressure_ratio": 0.6,
    "status": "completed"
  },
  "result_summary": {
    "outputs": [{ "alert_count": 1, "severe": 0, "warnings": 0 }],
    "status": "completed"
  }
}
```

The full record additionally contains capability bindings, per-hop work metrics vs. budgets, and presentation views.

## Repository Map

| Path | Purpose |
| ---- | ------- |
| `core_reference.json` | Architectural foundation: invariants I1–I4, quality contracts, error registry |
| `behavioral_directives.json` | Behavioral protocols for AI agents working in this repository |
| `src/runtime/` | Tile runtime: substrate, registry, resolver, tiles, benchmarking, governance sync |
| `src/main.py` | CLI demo entry point |
| `tests/` | Pytest suite covering tiles, resolver, schemas, and governance sync |
| `ai_docs/` | JSON-first governance docs: contracts, protocols, scenario/playlist catalogs, dashboards, component index |
| `knowledge_base/` | Techniques, innovations, automation patterns, session history, automation-run ledger |
| `logs/` | Coverage snapshots and benchmark evidence bundles |
| `ui/benchmark_dashboard/` | React/Vite dashboard for benchmark results |
| `scripts/` | TinyLLaMA server startup script |
| `.github/workflows/` | CI: automation runner with governance-drift check |

## Scope and Limitations

### Supported

- Deterministic multi-hop resolution over the registered tile set, with proof records
- Pressure telemetry, severity-classified alerts, and chain-quality facts
- Benchmark scenario/playlist execution with evidence capture and dashboard generation
- Coverage sync into a machine-readable component index, enforced in CI
- Optional guarded generation through a locally hosted TinyLLaMA server

### Not Claimed

- Not a general-purpose agent framework or planner; capability chains come from a fixed, hand-registered tile set
- Not validated for production use, security-sensitive workloads, or concurrent multi-user operation
- The "proof records" are structured execution evidence, not formal verification
- The determinism guarantee does not extend to the TinyLLaMA-backed tile
- Not validated beyond the scenarios and inputs included in this repository

### Known Limitations

- **No packaging**: there is no `pyproject.toml` or `requirements.txt`; modules are run with `PYTHONPATH=src` rather than an installed package.
- **Local model dependency**: the imagination demo and the hallucinator benchmark scenario require a user-supplied GGUF model and llama.cpp build (not shipped).
- **Startup script is POSIX-only** (`scripts/start_tinyllama_server.sh`).
- Stored benchmark artifacts are dated 2026-01-25 and reflect the state at that time; regenerate them via the benchmarking runner to refresh.
- The benchmark dashboard UI is a viewer for generated JSON and has no automated tests.

## Documentation

- [SYSTEM_STATUS.md](SYSTEM_STATUS.md) — current operational state and gaps
- [SYSTEM_SUMMARY.md](SYSTEM_SUMMARY.md) — human-facing overview with the latest dashboard digest
- [ai_docs/component_index.json](ai_docs/component_index.json) — canonical component registry (19 components)
- [ai_docs/benchmarking_scenarios.json](ai_docs/benchmarking_scenarios.json) / [ai_docs/benchmarking_playlists.json](ai_docs/benchmarking_playlists.json) — benchmark catalogs
- [core_reference.json](core_reference.json) — invariants, contracts, and error registry
- [logs/benchmarks/](logs/benchmarks/) — stored benchmark evidence bundles
- [ui/benchmark_dashboard/README.md](ui/benchmark_dashboard/README.md) — dashboard UI notes

## Development Provenance

This project was developed through a human-directed, AI-assisted workflow. The repository's `knowledge_base/` (techniques, innovations, automation patterns, session history) and `.github/copilot-instructions.md` document the operating protocol, implementation sequence, and automation ledger. These records are provenance, not proof: the code and tests remain the authoritative implementation, and any conversational or historical claim should be checked against the repository's current state.

## Contributing

- Run validation with `python -m pytest tests/` before submitting changes.
- Governance JSON must stay synchronized: after runtime changes, run the automation runner with coverage sync (see Usage) and commit the updated `ai_docs/component_index.json` — CI rejects drift.
- Core-logic changes must preserve determinism (invariant I1 in `core_reference.json`): no randomness or timestamps in tile/resolver logic.
- Architectural rules are defined in `core_reference.json` and `behavioral_directives.json`.

## License

[MIT](LICENSE)
