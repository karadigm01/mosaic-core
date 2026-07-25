# System Summary

**Last Updated:** 2026-01-25T06:27:49Z  
**Total Components:** 19  
**System Health:** 19/19 healthy components (`ai_docs/component_index.json`)
**Test Suite:** **87/87** passing tests (`python -m runtime.automation_runner --pytest --sync-coverage`)

## Component Health Overview
- Runtime tiles remain stable with resolver 93.68 % coverage, semantic router 97.56 %, route dispatch 97.14 %, sentiment 98.04 %, pressure summary 100 %, pressure historian 97.92 %, proof evaluator 100 %, and guided hallucinator 100 % (component index metadata).
- Governance bundles (substrate contracts, lifecycle, sandbox specs, renderer profiles, sample promotion, system status) continue to report healthy status with 100 % schema coverage.
- CLI demos in `src/main.py` (`--demo sentiment` / `--demo imagination`) still provide deterministic repro paths for catalog scenarios, ensuring proof capture stays I1-compliant.
- `runtime.benchmarking_runner` now drives Phase 3 coverage by emitting scenario + playlist artifacts plus `ai_docs/benchmarking_dashboard.json` on every playlist invocation.

## Recent Changes
- Phase 3 playlists landed: baseline `logs/benchmarks/playlist.playlist.phase3_observability-20260125T062643Z.json` and regression `logs/benchmarks/playlist.playlist.phase3_regression-20260125T062749Z.json` each executed 3/3 scenarios with zero failures while recording pytest hooks for dashboard validation.
- Scenario evidence bundles for both runs (`logs/benchmarks/scenario.sentiment_chain-20260125T062615Z.json`, `logs/benchmarks/scenario.hallucinator_imagination-20260125T062643Z.json`, `logs/benchmarks/scenario.pressure_alert-20260125T062643Z.json`, `logs/benchmarks/scenario.hallucinator_imagination-20260125T062748Z.json`, `logs/benchmarks/scenario.sentiment_chain-20260125T062749Z.json`, `logs/benchmarks/scenario.pressure_alert-20260125T062749Z.json`) include proofs, presentation views, and TinyLLaMA telemetry feeding the new governance diffs.
- `ai_docs/benchmarking_dashboard.json` reflects the Phase 3 regression run (latency span 41 ms, pytest_targets=2) and automatically archives timestamped snapshots (`ai_docs/benchmarking_dashboard.20260125T062643Z.json`, `.20260125T062749Z.json`) for history diffs.
- `python -m runtime.benchmark_dashboard_cli --update-system-status` now rewrites the dashboard section inside `SYSTEM_STATUS.md`, so governance markdown stays consistent with the latest JSON output without manual edits.
- `knowledge_base/kb_index.json` refreshed to 54 total automations (52 success / 1 failed / 1 skipped, success rate ≈ 0.963) and captures the newest TinyLLaMA probe (1 ms, HTTP 200 at 1769322468.8988614).

### Benchmarking Dashboard Digest
<!-- dashboard-summary:begin -->
### Dashboard Highlights

- Playlist `playlist.phase3_regression` run `auto-0007-run-playlist.playlist.phase3_regression-20260725T205117Z` captured 3 scenarios with 0 failures and latency span 30 ms.
- Coverage snapshot lists 0 failing scenarios and 2 pytest targets.
- Diff baseline `logs/benchmarks/playlist.playlist.phase3_regression-20260125T062749Z.json` with aggregate delta {'failures': 0, 'tinyllama_latency_max_ms': -11, 'tinyllama_latency_min_ms': 0, 'total_duration_seconds': 0}; archival artifact `logs/benchmarks/playlist.playlist.phase3_regression-20260725T205117Z.json`.
- Scenario coverage distribution -> full: scenario.hallucinator_imagination, scenario.pressure_alert, scenario.sentiment_chain
- Regressions detected: scenario.hallucinator_imagination (latency_delta_ms=-11)
- Previous snapshot reference `logs/benchmarks/history/dashboard.playlist.test-auto-0007-run-playlist.playlist.test-20260725T205346Z.json`
- Replay cadence => 0 runs (last `n/a`); remediation backlog 0.
<!-- dashboard-summary:end -->

## Knowledge Base Statistics
- Techniques: 20  
- Bug Fixes: 0  
- Innovations: 11  
- Automation Patterns: 7 (`auto-0007 Benchmark Scenario Evidence Capture` governs playlist logging)
- Automation Metrics: `total_automated_actions = 54`, `successful_automations = 52`, `failed_automations = 1`, `success_rate ≈ 0.963` (`knowledge_base/kb_index.json`).

## Recent Innovations
- `innov-0011 Severity-Governed Pressure Alerts` (2026-01-18) continues to anchor Phase 2 pressure telemetry—its deterministic escalation rules are exercised in the latest `scenario.pressure_alert` evidence bundle.

## Current Session Activity
- Ran both Phase 3 playlists through `runtime.benchmarking_runner`, capturing scenario evidence, playlist bundles, and automation ledger entries for pattern `auto-0007`.
- Regenerated dashboard + history snapshots, triggered `benchmark_dashboard_cli --update-system-status`, and archived the JSON outputs under `ai_docs/benchmarking_dashboard.*` for governance diffs.
- Updated `knowledge_base/kb_index.json`, `SYSTEM_STATUS.md`, and `SYSTEM_SUMMARY.md` so stakeholder-facing metrics match the new Phase 3 evidence.
- Session references retained for traceability (latest history includes `session-20260124-001` + `session-20260125-001`).


