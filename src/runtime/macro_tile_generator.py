"""Macro tile generator for resolver-delegated wrappers."""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

from runtime import component_registry_sync

DEFAULT_CATALOG_PATH = Path("ai_docs/example_tiles.json")
DEFAULT_SCHEMA_PATH = Path("ai_docs/substrate_contracts.json")
DEFAULT_MODULE_DIR = Path("src/runtime/synthesized_tiles")
DEFAULT_DOC_DIR = Path("ai_docs/synthesized_tiles")
DEFAULT_TEST_DIR = Path("tests/synthesized_tiles")
DEFAULT_PATCH_DIR = Path("ai_docs/synthesized_tiles/registry_patches")


@dataclass
class TileSpec:
    tile_id: str
    capabilities: List[str]
    inputs: List[Dict[str, Any]]
    outputs: List[Dict[str, Any]]
    behavior_guarantees: Dict[str, Any]
    resource_budget: Dict[str, float]
    presentation_manifest: Dict[str, Any]
    lifecycle_state: str
    constraints_compliance: List[str]
    tile_name: str | None = None

    @property
    def input_types(self) -> List[str]:
        return [entry.get("fact_type") for entry in self.inputs if entry.get("fact_type")]

    @property
    def output_types(self) -> List[str]:
        return [entry.get("fact_type") for entry in self.outputs if entry.get("fact_type")]


@dataclass
class ResourcePolicy:
    max_cpu_percent: float
    max_latency_p95_ms: float


def load_tile_catalog(path: Path) -> Dict[str, TileSpec]:
    data = json.loads(path.read_text(encoding="utf-8"))
    specs = {}
    for entry in data.get("tiles", []):
        spec = TileSpec(
            tile_id=entry["tile_id"],
            capabilities=list(entry.get("capabilities", [])),
            inputs=list(entry.get("inputs", [])),
            outputs=list(entry.get("outputs", [])),
            behavior_guarantees=dict(entry.get("behavior_guarantees", {})),
            resource_budget=dict(entry.get("resource_budget", {})),
            presentation_manifest=dict(entry.get("presentation_manifest", {})),
            lifecycle_state=entry.get("lifecycle_state", "proposed"),
            constraints_compliance=list(entry.get("constraints_compliance", [])),
            tile_name=entry.get("tile_name"),
        )
        specs[spec.tile_id] = spec
    return specs


def load_resource_policy(path: Path) -> ResourcePolicy:
    data = json.loads(path.read_text(encoding="utf-8"))
    policies = data.get("resource_policies", {})
    latency_ceiling = 50.0
    for rule in policies.get("governor_rules", []):
        if "latency_p95_ms" not in rule:
            continue
        match = re.search(r"latency_p95_ms\s*[><=]+\s*(\d+)", rule)
        if match:
            latency_ceiling = float(match.group(1))
            break
    return ResourcePolicy(
        max_cpu_percent=float(policies.get("max_per_resource_utilization_percent", 30.0)),
        max_latency_p95_ms=latency_ceiling,
    )


def validate_tiles_exist(plan: Sequence[str], catalog: Dict[str, TileSpec]) -> List[TileSpec]:
    missing = [tile_id for tile_id in plan if tile_id not in catalog]
    if missing:
        raise ValueError(f"tiles not found in catalog: {', '.join(missing)}")
    return [catalog[tile_id] for tile_id in plan]


def validate_lifecycle(plan_tiles: Sequence[TileSpec]) -> None:
    not_promoted = [spec.tile_id for spec in plan_tiles if spec.lifecycle_state != "promoted"]
    if not_promoted:
        raise ValueError(
            "capability plan requires promoted tiles, but these are not promoted: " + ", ".join(not_promoted)
        )


def validate_chain(plan_tiles: Sequence[TileSpec]) -> None:
    for current_spec, next_spec in zip(plan_tiles, plan_tiles[1:]):
        current_outputs = set(current_spec.output_types)
        next_inputs = set(next_spec.input_types)
        if current_outputs and next_inputs and current_outputs.intersection(next_inputs):
            continue
        raise ValueError(
            f"tile {current_spec.tile_id} outputs {sorted(current_outputs)} incompatible with inputs of {next_spec.tile_id}"
        )


def aggregate_resource_budget(plan_tiles: Sequence[TileSpec]) -> Dict[str, float]:
    totals: Dict[str, float] = {"cpu_percent": 0.0, "memory_mb": 0.0, "disk_mb": 0.0, "latency_p95_ms": 0.0}
    for spec in plan_tiles:
        budget = spec.resource_budget
        for key in totals:
            totals[key] += float(budget.get(key, 0.0))
    return totals


def validate_resource_budget(budget: Dict[str, float], policy: ResourcePolicy) -> None:
    if budget.get("cpu_percent", 0.0) > policy.max_cpu_percent:
        raise ValueError(
            f"aggregated cpu_percent {budget['cpu_percent']} exceeds policy ceiling {policy.max_cpu_percent}"
        )
    if budget.get("latency_p95_ms", 0.0) > policy.max_latency_p95_ms:
        raise ValueError(
            f"aggregated latency_p95_ms {budget['latency_p95_ms']} exceeds policy ceiling {policy.max_latency_p95_ms}"
        )


def derive_capability_plan(plan_tiles: Sequence[TileSpec]) -> List[str]:
    plan: List[str] = []
    for spec in plan_tiles:
        if not spec.capabilities:
            raise ValueError(f"tile {spec.tile_id} is missing capability definitions")
        plan.append(spec.capabilities[0])
    return plan


def aggregate_constraints(plan_tiles: Sequence[TileSpec]) -> List[str]:
    constraints: set[str] = set()
    for spec in plan_tiles:
        constraints.update(spec.constraints_compliance)
    return sorted(constraints)


def infer_name_from_tile_id(tile_id: str) -> str:
    tokens = re.split(r"[^a-zA-Z0-9]", tile_id)
    return "".join(token.capitalize() for token in tokens if token) + "MacroTile"


def sanitize_identifier(tile_id: str) -> str:
    return tile_id.replace('.', '_').replace('-', '_')


def build_module_source(
    class_name: str,
    tile_id: str,
    tile_name: str,
    capability_plan: List[str],
    constraints: List[str],
    input_types: List[str],
    output_type: str,
) -> str:
    plan_literal = ", ".join(f"\"{cap}\"" for cap in capability_plan)
    constraints_literal = ", ".join(f"\"{c}\"" for c in constraints)
    input_literal = ", ".join(f"\"{fact}\"" for fact in input_types)
    return f"""\
from __future__ import annotations

from runtime.constraint_substrate import ConstraintFact
from runtime.resolver import Goal, Resolver
from runtime.semantic_router import TileExecutionResult


class {class_name}:
    \"\"\"Synthesized macro tile delegating to resolver for capability plan execution.\"\"\"

    TILE_ID = \"{tile_id}\"
    TILE_NAME = \"{tile_name}\"
    CAPABILITY_PLAN = [{plan_literal}]
    INPUT_TYPES = [{input_literal}]
    OUTPUT_TYPE = \"{output_type}\"
    CONSTRAINTS = [{constraints_literal}]

    def __init__(self, resolver: Resolver) -> None:
        self._resolver = resolver

    def execute(self, fact: ConstraintFact) -> TileExecutionResult:
        if fact.fact_type not in self.INPUT_TYPES:
            raise ValueError(f\"fact type {fact.fact_type} not supported by {self.TILE_ID}\")
        goal = Goal(
            goal_id=f\"macro::{tile_id}::{fact.fact_id}\",
            desired_output=self.CAPABILITY_PLAN[-1],
            input_fact_ids=[fact.fact_id],
            constraints=self.CONSTRAINTS,
            capability_plan=self.CAPABILITY_PLAN,
        )
        proof = self._resolver.resolve(goal)
        outputs = list(proof.result_summary.get(\"outputs\") or [])
        if not outputs:
            raise ValueError(f\"resolver returned no outputs for proof {proof.proof_id}\")
        payload = outputs[-1]
        macro_fact = ConstraintFact(
            fact_id=f\"{tile_id}::{{proof.proof_id}}\",
            fact_type=self.OUTPUT_TYPE,
            payload=payload,
            confidence=1.0,
            ttl_seconds=300,
            provenance={"tile": self.TILE_ID, "delegate_plan": self.CAPABILITY_PLAN},
            constraints_compliance=self.CONSTRAINTS,
        )
        work_metrics = {
            "delegated_hops": float(len(self.CAPABILITY_PLAN)),
            "macro_tile": 1.0,
        }
        return TileExecutionResult(macro_fact, work_metrics)
"""


def build_component_doc(
    tile_id: str,
    tile_name: str,
    plan_capabilities: List[str],
    plan_tiles: Sequence[TileSpec],
    resource_budget: Dict[str, float],
    constraints: List[str],
    inputs: List[Dict[str, Any]],
    outputs: List[Dict[str, Any]],
    generated_by: str,
    timestamp: str,
    lifecycle_state: str,
) -> Dict[str, Any]:
    return {
        "component_id": tile_id,
        "component_name": tile_name,
        "component_type": "runtime_module",
        "origin": "synthesized",
        "capability_plan": plan_capabilities,
        "delegate_resolver": True,
        "synthesis_manifest": {
            "generated_at": timestamp,
            "generated_by": generated_by,
            "source_tiles": [
                {
                    "tile_id": spec.tile_id,
                    "capabilities": spec.capabilities,
                    "lifecycle_state": spec.lifecycle_state,
                    "resource_budget": spec.resource_budget,
                }
                for spec in plan_tiles
            ],
        },
        "contract": {
            "tile_id": tile_id,
            "capabilities": list(plan_tiles[-1].capabilities),
            "inputs": inputs,
            "outputs": outputs,
            "behavior_guarantees": {
                "determinism_proof_hash": "hash://macro/delegated",
                "delegated_tiles": [spec.tile_id for spec in plan_tiles],
            },
            "resource_budget": resource_budget,
            "presentation_manifest": plan_tiles[-1].presentation_manifest,
            "lifecycle_state": lifecycle_state,
            "constraints_compliance": constraints,
        },
    }


def build_registry_entry(
    tile_id: str,
    plan_tiles: Sequence[TileSpec],
    resource_budget: Dict[str, float],
    inputs: List[str],
    outputs: List[str],
) -> Dict[str, Any]:
    return {
        "tile_id": tile_id,
        "capabilities": list(plan_tiles[-1].capabilities),
        "resource_budget": resource_budget,
        "input_types": inputs,
        "output_types": outputs,
        "constraints": plan_tiles[-1].constraints_compliance,
        "delegate_resolver": True,
        "source_tiles": [spec.tile_id for spec in plan_tiles],
    }


def write_text_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_json_file(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_test_source(module_path: str, class_name: str, capability_plan: List[str]) -> str:
    plan_literal = "[" + ", ".join(f"\"{cap}\"" for cap in capability_plan) + "]"
    template = """\
from __future__ import annotations

from types import SimpleNamespace

from runtime.constraint_substrate import ConstraintFact, ProofRecord, TileInvocation
from runtime.semantic_router import TileExecutionResult

from {module_path} import {class_name}


def _fake_proof() -> ProofRecord:
    return ProofRecord(
        proof_id="proof::macro::test",
        goal={{"goal_id": "macro::goal"}},
        constraint_context={{"requested_invariants": ["I1", "I2", "I3", "I4"]}},
        tile_sequence=[TileInvocation(tile_id="tile.test", inputs=["fact.input"], outputs=["fact.output"])],
        capability_bindings=[],
        resource_usage={{}},
        result_summary={{"outputs": [{{"text": "ok"}}]}},
        presentation_views=[],
        ledger_metadata={{}},
        audit_hash=None,
    )


def test_macro_tile_constructs_goal_and_fact() -> None:
    resolver = SimpleNamespace()
    proof = _fake_proof()
    holder = {{}}

    def _resolve(goal):
        holder["goal"] = goal
        return proof

    resolver.resolve = _resolve
    tile = {class_name}(resolver)
    fact = ConstraintFact(
        fact_id="fact.input",
        fact_type=tile.INPUT_TYPES[0],
        payload={{"text": "hello world"}},
        confidence=1.0,
        ttl_seconds=60,
        provenance={{"tile": "test"}},
        constraints_compliance=["I1", "I2", "I3", "I4"],
    )
    result = tile.execute(fact)
    assert isinstance(result, TileExecutionResult)
    assert holder["goal"].capability_plan == {plan_literal}
    assert result.fact.fact_type == tile.OUTPUT_TYPE
    assert result.fact.payload == proof.result_summary["outputs"][0]
    assert result.work_metrics["delegated_hops"] == float(len(tile.CAPABILITY_PLAN))
"""
    return template.format(module_path=module_path, class_name=class_name, plan_literal=plan_literal)


def iso_timestamp(explicit: str | None = None) -> str:
    if explicit:
        return explicit
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def generate_macro_tile(
    tile_id: str,
    tile_name: str,
    plan_tile_ids: Sequence[str],
    catalog_path: Path,
    schema_path: Path,
    module_dir: Path,
    doc_dir: Path,
    test_dir: Path,
    patch_dir: Path,
    generated_by: str,
    timestamp: str | None = None,
    lifecycle_state: str = "proposed",
) -> Dict[str, Path]:
    catalog = load_tile_catalog(catalog_path)
    plan_tiles = validate_tiles_exist(plan_tile_ids, catalog)
    validate_lifecycle(plan_tiles)
    validate_chain(plan_tiles)
    policy = load_resource_policy(schema_path)
    budget = aggregate_resource_budget(plan_tiles)
    validate_resource_budget(budget, policy)
    capability_plan = derive_capability_plan(plan_tiles)
    constraints = aggregate_constraints(plan_tiles)
    input_specs = plan_tiles[0].inputs
    output_specs = plan_tiles[-1].outputs
    if not output_specs:
        raise ValueError(f"tile {plan_tiles[-1].tile_id} is missing outputs")
    if not input_specs:
        raise ValueError(f"tile {plan_tiles[0].tile_id} is missing inputs")
    input_types = [entry.get("fact_type") for entry in input_specs if entry.get("fact_type")]
    output_types = [entry.get("fact_type") for entry in output_specs if entry.get("fact_type")]
    if not input_types or not output_types:
        raise ValueError("input or output fact types missing from catalog")
    class_name = infer_name_from_tile_id(tile_id)
    module_name = sanitize_identifier(tile_id)
    module_path = module_dir / f"{module_name}.py"
    test_module_import = f"runtime.synthesized_tiles.{module_name}"
    test_path = test_dir / f"test_{module_name}.py"
    doc_path = doc_dir / f"{module_name}.json"
    patch_path = patch_dir / f"{module_name}.json"
    timestamp_value = iso_timestamp(timestamp)

    module_source = build_module_source(
        class_name=class_name,
        tile_id=tile_id,
        tile_name=tile_name,
        capability_plan=capability_plan,
        constraints=constraints,
        input_types=input_types,
        output_type=output_types[0],
    )
    doc_payload = build_component_doc(
        tile_id=tile_id,
        tile_name=tile_name,
        plan_capabilities=capability_plan,
        plan_tiles=plan_tiles,
        resource_budget=budget,
        constraints=constraints,
        inputs=input_specs,
        outputs=output_specs,
        generated_by=generated_by,
        timestamp=timestamp_value,
        lifecycle_state=lifecycle_state,
    )
    registry_entry = build_registry_entry(
        tile_id=tile_id,
        plan_tiles=plan_tiles,
        resource_budget=budget,
        inputs=input_types,
        outputs=output_types,
    )
    test_source = build_test_source(test_module_import, class_name, capability_plan)

    write_text_file(module_path, module_source)
    write_json_file(doc_path, doc_payload)
    write_text_file(test_path, test_source)
    write_json_file(patch_path, registry_entry)

    return {
        "module": module_path,
        "doc": doc_path,
        "test": test_path,
        "registry_patch": patch_path,
    }


def register_macro_tile_doc(doc_path: Path, index_path: Path, workspace_root: Path | None = None) -> Dict[str, Any]:
    payload = json.loads(doc_path.read_text(encoding="utf-8"))
    lifecycle_state = (payload.get("contract") or {}).get("lifecycle_state")
    if lifecycle_state != "promoted":
        raise ValueError("macro tile must be promoted before registering in component index")
    return component_registry_sync.register_component(doc_path, index_path, workspace_root)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate resolver-delegated macro tile artifacts.")
    parser.add_argument("tile_id", help="Tile identifier, e.g., tile.macro.sentiment_chain")
    parser.add_argument("tile_name", help="Human-readable tile name")
    parser.add_argument("plan", nargs="+", help="Ordered tile IDs representing the capability chain")
    parser.add_argument("--generated-by", default="unknown", help="Provenance marker recorded in manifest")
    parser.add_argument("--catalog-path", type=Path, default=DEFAULT_CATALOG_PATH)
    parser.add_argument("--schema-path", type=Path, default=DEFAULT_SCHEMA_PATH)
    parser.add_argument("--module-dir", type=Path, default=DEFAULT_MODULE_DIR)
    parser.add_argument("--doc-dir", type=Path, default=DEFAULT_DOC_DIR)
    parser.add_argument("--test-dir", type=Path, default=DEFAULT_TEST_DIR)
    parser.add_argument("--patch-dir", type=Path, default=DEFAULT_PATCH_DIR)
    parser.add_argument("--timestamp", default=None, help="Override ISO timestamp for deterministic generation")
    parser.add_argument(
        "--lifecycle-state",
        default="proposed",
        choices=["proposed", "sandboxed", "promoted"],
        help="Lifecycle state stored in the synthesized contract (default: proposed)",
    )
    parser.add_argument(
        "--register-component",
        action="store_true",
        help="Register the component doc in component_index.json when lifecycle_state=promoted",
    )
    parser.add_argument(
        "--component-index",
        type=Path,
        default=Path("ai_docs/component_index.json"),
        help="Component index path for registration (default: ai_docs/component_index.json)",
    )
    parser.add_argument(
        "--workspace-root",
        type=Path,
        default=None,
        help="Optional workspace root for computing relative paths during registration",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    artifacts = generate_macro_tile(
        tile_id=args.tile_id,
        tile_name=args.tile_name,
        plan_tile_ids=args.plan,
        catalog_path=args.catalog_path,
        schema_path=args.schema_path,
        module_dir=args.module_dir,
        doc_dir=args.doc_dir,
        test_dir=args.test_dir,
        patch_dir=args.patch_dir,
        generated_by=args.generated_by,
        timestamp=args.timestamp,
        lifecycle_state=args.lifecycle_state,
    )
    if args.register_component:
        register_macro_tile_doc(
            artifacts["doc"],
            args.component_index,
            args.workspace_root,
        )
    summary = "\n".join(f"{label}: {path}" for label, path in artifacts.items())
    print(summary)


if __name__ == "__main__":  # pragma: no cover - manual invocation
    main()
