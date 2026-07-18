# System Status

**Generated:** 2026-01-25

## Component Health
- 19/19 components healthy in `ai_docs/component_index.json` (schema version 2.0.0); all marked I1–I4 compliant.
- Runtime coverage (from component index): resolver_skeleton 93.68; semantic_router_tile 97.56; route_dispatch_tile 97.14; alert_panel_tile 100.0; sentiment_tile 98.04; proof_evaluator_tile 100.0; pressure_historian_tile 97.92; pressure_summary_tile 100.0; guided_hallucinator_tile 100.0.
- Governance bundles (`substrate_contracts`, `audit_ledger_schema`, `tile_lifecycle_protocol`, `example_tiles`, `sandbox_*`, `audit_query_api`, `presentation_renderer_profiles`, `sample_tile_promotion`, `system_status_report`) remain healthy with recorded coverage 100% per index.
- Resolver stack (semantic router → route dispatch → alert panel) continues to anchor dependents; no degraded nodes reported.

## Tests & Automation
- Latest automation metrics (`knowledge_base/kb_index.json`): 54 automated actions (52 success, 1 failed, 1 skipped), success rate ≈ 0.963.
- Constraint compliance counters: I1=20, I2=20, I3=20, I4=20, all compliant.
- Bench and resolver test coverage referenced from component index; no new pytest run executed in this session. Pending action: rerun full suite before next promotion.
- Automation evidence reference: auto-0003-run-20260124T212057 (coverage snapshot 95.68%).

## Schema Integrity
- Schema bundles `ai_docs/substrate_contracts.json` and `ai_docs/audit_ledger_schema.json` validated in prior runs; no known issues recorded in component index or knowledge base.
- Component index metadata last_updated 2026-01-25T01:26:14Z; referential integrity intact (dependencies resolved, no orphaned entries reported).

## Resolver Capabilities & Resiliency
- Deterministic multi-hop resolver with capability graph (semantic routing → dispatch → presentation) backed by per-hop work metrics and pressure telemetry.
- Alerting pipeline (pressure signals → severity → alert panel) remains deterministic and presentation-ready; proofs include chain_quality and pressure_history facts via meta tiles.
- Guided hallucinator tile exposed through resolver with guardrails; coverage registered at 100.0 in index.

## Knowledge Base Snapshot
- Techniques: 21; Innovations: 11; Automation patterns: 7.
- Latest TinyLLaMA health snapshot: available=true, latency_ms=1, status_code=200 (probed at 1769322468.8988614).
- Automation lookup indices populated for documentation, validation, and constraints; no unresolved error codes recorded.

## Gaps and Risks
- Component index not yet refreshed after recent macro tile generator and dashboard wiring; register those runtime/services modules once governance review completes.
- Test suite not rerun this session; status assumes prior automation evidence—risk of drift until next execution.
- Benchmark coverage relies on recorded evidence; `hallucinator_imagination` scenario may still lack telemetry alias coverage until dashboard is refreshed.

## Invariant Check
- I1–I4 compliance upheld per component index and kb_index counters; no outstanding violations or remediation tickets.

## Next Actions
1) Refresh component index to register macro tile generator + dashboard service changes and update `last_updated` metadata.
2) Rerun full pytest + automation runner to confirm coverage and regenerate ledger evidence.
3) Regenerate benchmarking dashboard snapshot and align telemetry aliases (hallucinator coverage) before next promotion decision.
