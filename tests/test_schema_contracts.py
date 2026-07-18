from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import pytest

ROOT = Path(__file__).resolve().parents[1]
GOVERNANCE_COVERAGE_PATH = ROOT / "logs" / "governance-coverage.json"
_GOVERNANCE_FILES: set[str] = set()


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load(rel_path: str) -> dict:
    absolute = ROOT.joinpath(rel_path)
    with absolute.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    _GOVERNANCE_FILES.add(rel_path)
    return payload


def _read_text(rel_path: str) -> str:
    absolute = ROOT.joinpath(rel_path)
    _GOVERNANCE_FILES.add(rel_path)
    return absolute.read_text(encoding="utf-8")


@pytest.fixture(scope="session", autouse=True)
def _record_governance_coverage() -> Iterator[None]:
    yield
    if not _GOVERNANCE_FILES:
        return
    data = {
        "generated_at": _utc_timestamp(),
        "files": sorted(_GOVERNANCE_FILES),
    }
    GOVERNANCE_COVERAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    GOVERNANCE_COVERAGE_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def test_audit_ledger_schema_has_required_sections() -> None:
    data = _load("ai_docs/audit_ledger_schema.json")
    assert data.get("component_id") == "audit_ledger_schema"
    schemas = data.get("schemas", {})
    for key in [
        "ledger_root",
        "ledger_entry",
        "pressure_signal",
        "pressure_alert",
        "integrity_proof",
    ]:
        assert key in schemas
        schema = schemas[key]
        assert schema.get("required_fields"), f"missing required_fields for {key}"
        assert schema.get("field_specs"), f"missing field_specs for {key}"


def test_presentation_renderers_define_alert_requirements() -> None:
    data = _load("ai_docs/presentation_renderer_profiles.json")
    renderers = data.get("renderers", [])
    assert renderers, "no renderer definitions present"
    for renderer in renderers:
        assert renderer.get("renderer_id")
        assert renderer.get("data_requirements"), f"renderer {renderer['renderer_id']} missing data requirements"
        ui_contract = renderer.get("ui_contract", {})
        assert ui_contract.get("layout"), f"renderer {renderer['renderer_id']} missing layout"


def test_example_tiles_have_core_fields() -> None:
    data = _load("ai_docs/example_tiles.json")
    for tile in data.get("tiles", []):
        assert tile.get("tile_id")
        assert tile.get("capabilities"), f"tile {tile['tile_id']} missing capabilities"
        assert tile.get("inputs"), f"tile {tile['tile_id']} missing inputs"
        assert tile.get("outputs"), f"tile {tile['tile_id']} missing outputs"
        assert tile.get("resource_budget"), f"tile {tile['tile_id']} missing resource budget"


def test_component_index_metadata_matches_counts() -> None:
    data = _load("ai_docs/component_index.json")
    component_total = len(data.get("components", []))
    metadata_total = data.get("metadata", {}).get("total_components")
    assert component_total == metadata_total, "component_index metadata total mismatch"
    health = data.get("health_status", {})
    healthy = health.get("total_healthy", 0)
    degraded = health.get("total_degraded", 0)
    failing = health.get("total_failing", 0)
    assert component_total == healthy + degraded + failing, "health counts do not sum to total"


def test_tile_lifecycle_protocol_defines_governance_states() -> None:
    data = _load("ai_docs/tile_lifecycle_protocol.json")
    states = data.get("lifecycle_states", [])
    assert states, "lifecycle states missing"
    for state in states:
        assert state.get("state"), "state name required"
        assert state.get("entry_criteria"), f"entry criteria missing for {state}"
        assert state.get("exit_requirements"), f"exit requirements missing for {state}"
        assert state.get("evidence_artifacts"), f"evidence artifacts missing for {state}"
    hooks = data.get("governance_hooks", {})
    assert hooks.get("ledger_requirements"), "ledger requirements missing"


def test_substrate_contracts_bundle_lists_core_schemas() -> None:
    data = _load("ai_docs/substrate_contracts.json")
    schemas = data.get("schemas", {})
    for required in [
        "constraint_fact",
        "reasoning_tile_contract",
        "capability_descriptor",
        "proof_record",
        "presentation_manifest",
    ]:
        schema = schemas.get(required)
        assert schema, f"schema {required} missing"
        assert schema.get("required_fields"), f"required_fields missing for {required}"
        assert schema.get("field_specs"), f"field_specs missing for {required}"


def test_sandbox_test_suite_profiles_have_assertions() -> None:
    data = _load("ai_docs/sandbox_test_suite.json")
    profiles = data.get("test_profiles", [])
    assert profiles, "no sandbox profiles defined"
    for profile in profiles:
        assert profile.get("profile_id"), "profile missing id"
        assert profile.get("assertions"), f"assertions missing for profile {profile}"
        assert profile.get("evidence"), f"evidence missing for profile {profile}"


def test_sandbox_automation_protocol_has_stages() -> None:
    data = _load("ai_docs/sandbox_automation_protocol.json")
    flow = data.get("automation_flow", {})
    stages = flow.get("stages", [])
    assert flow.get("trigger_events"), "automation triggers missing"
    assert stages, "automation stages missing"
    for stage in stages:
        assert stage.get("name"), "stage name missing"
        assert stage.get("inputs"), f"inputs missing for stage {stage}"
        assert stage.get("outputs"), f"outputs missing for stage {stage}"
        assert stage.get("failure_policy"), f"failure policy missing for stage {stage}"


def test_audit_query_api_endpoints_have_authz() -> None:
    data = _load("ai_docs/audit_query_api.json")
    endpoints = data.get("endpoints", [])
    assert endpoints, "no endpoints defined"
    for endpoint in endpoints:
        assert endpoint.get("name") and endpoint.get("method") and endpoint.get("path"), "endpoint missing basic metadata"
        assert endpoint.get("request_schema"), f"request schema missing for {endpoint}"
        assert endpoint.get("response_schema"), f"response schema missing for {endpoint}"
    authz = data.get("authz_policies", {})
    assert authz.get("roles"), "auth roles missing"
    assert authz.get("permissions"), "auth permissions missing"


def test_sample_tile_promotion_runbook_is_ordered() -> None:
    data = _load("ai_docs/sample_tile_promotion.json")
    steps = data.get("steps", [])
    assert steps, "promotion steps missing"
    orders = [step.get("order") for step in steps]
    assert orders == sorted(orders), "promotion steps must be ordered"
    for step in steps:
        assert step.get("state"), "state missing in step"
        assert step.get("actions"), f"actions missing for step {step}"
        assert step.get("evidence"), f"evidence missing for step {step}"


def test_sample_tile_promotion_states_match_lifecycle_protocol() -> None:
    lifecycle = _load("ai_docs/tile_lifecycle_protocol.json")
    lifecycle_states = lifecycle.get("lifecycle_states", [])
    assert lifecycle_states, "lifecycle protocol missing states"
    lifecycle_order = {state["state"]: idx for idx, state in enumerate(lifecycle_states)}

    runbook = _load("ai_docs/sample_tile_promotion.json")
    steps = runbook.get("steps", [])
    assert steps, "promotion steps missing"
    step_states = [step.get("state") for step in steps]
    assert set(step_states).issubset(lifecycle_order), "runbook references unknown lifecycle state"

    state_positions = [lifecycle_order[state] for state in step_states]
    assert state_positions == sorted(state_positions), "runbook states out of lifecycle order"


def test_runbook_references_sandbox_outputs() -> None:
    automation = _load("ai_docs/sandbox_automation_protocol.json")
    stages = automation.get("automation_flow", {}).get("stages", [])
    assert stages, "sandbox automation has no stages"
    stage_outputs: set[str] = set()
    for stage in stages:
        stage_outputs.update(stage.get("outputs", []))

    runbook = _load("ai_docs/sample_tile_promotion.json")
    evidence = {
        artifact
        for step in runbook.get("steps", [])
        for artifact in step.get("evidence", [])
    }
    required = {"sandbox_result_set", "ledger_entry_id"}
    assert required.issubset(stage_outputs), "automation flow missing required artifacts"
    assert required.issubset(evidence), "runbook missing evidence references from automation flow"


def test_audit_query_api_operations_align_with_contract() -> None:
    ledger = _load("ai_docs/audit_ledger_schema.json")
    contract_ops = set(
        ledger.get("presentation_hooks", {})
        .get("query_api_contract", {})
        .get("operations", [])
    )
    assert contract_ops, "ledger contract operations missing"

    api = _load("ai_docs/audit_query_api.json")
    endpoint_names = {endpoint.get("name") for endpoint in api.get("endpoints", [])}
    assert endpoint_names, "audit query API missing endpoints"
    assert contract_ops == endpoint_names, "ledger operations and API endpoints diverge"


def test_tiles_with_manifests_cover_manifest_profile() -> None:
    suite = _load("ai_docs/sandbox_test_suite.json")
    manifest_profiles = [
        profile
        for profile in suite.get("test_profiles", [])
        if profile.get("profile_id") == "sandbox.presentation_manifest"
    ]
    assert manifest_profiles, "manifest profile missing"
    profile = manifest_profiles[0]
    assert profile.get("applicability") == "tiles_with_manifest"

    tiles = _load("ai_docs/example_tiles.json").get("tiles", [])
    tiles_with_manifest = [tile for tile in tiles if tile.get("presentation_manifest")]
    assert tiles_with_manifest, "expected tiles with presentation manifests"
    for tile in tiles_with_manifest:
        manifest = tile["presentation_manifest"]
        assert manifest.get("preferred_views"), f"preferred_views missing for tile {tile['tile_id']}"
        assert manifest.get("data_bindings"), f"data_bindings missing for tile {tile['tile_id']}"


def test_system_status_references_latest_automation_run() -> None:
    status_doc = _read_text("SYSTEM_STATUS.md")
    assert "**Generated:** 2026-01-25" in status_doc
    assert "auto-0003-run-20260124T212057" in status_doc
    assert "95.68%" in status_doc, "status report missing coverage summary"


def test_system_summary_matches_component_totals() -> None:
    summary_doc = _read_text("SYSTEM_SUMMARY.md")
    assert "**Total Components:** 19" in summary_doc
    assert "**87/87** passing tests" in summary_doc
    assert "session-20260124-001" in summary_doc


def test_knowledge_base_automation_metrics_match_ledger() -> None:
    ledger = _load("knowledge_base/automation_runs/index.json")
    runs = ledger.get("runs", [])
    total = len(runs)
    success = sum(1 for run in runs if run.get("status") == "success")
    failed = sum(1 for run in runs if run.get("status") == "failed")

    kb_index = _load("knowledge_base/kb_index.json")
    metrics = kb_index.get("automation_success_metrics", {})
    assert metrics.get("total_automated_actions") == total
    assert metrics.get("successful_automations") == success
    assert metrics.get("failed_automations") == failed
