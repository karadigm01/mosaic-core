"""Utilities for syncing component documentation into the component index."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from .governance_automation import ComponentEntry, ComponentIndex, ensure_component_registration

ComponentDoc = Dict[str, Any]


def register_component(component_path: Path, index_path: Path, workspace_root: Optional[Path] = None) -> ComponentIndex:
    """Register or update a component entry inside the component index file."""
    component_data = _load_json(component_path)
    index_data = _load_json(index_path)
    entry = build_component_entry(component_data, component_path, workspace_root)
    updated = ensure_component_registration(index_data, entry)
    _write_json(index_path, updated)
    return updated


def build_component_entry(component_doc: ComponentDoc, component_path: Path, workspace_root: Optional[Path] = None) -> ComponentEntry:
    """Derive a component index entry from a component documentation JSON blob."""
    component_id = _require(component_doc, "component_id")
    component_name = _require(component_doc, "component_name")
    component_type = _require(component_doc, "component_type")
    creation_timestamp = component_doc.get("creation_timestamp", "1970-01-01T00:00:00Z")
    last_modified_timestamp = component_doc.get("last_modified_timestamp", creation_timestamp)
    dependencies = _ensure_list(component_doc.get("dependencies", []))
    dependents = _ensure_list(component_doc.get("dependents", []))
    health_status = component_doc.get("health_status", "healthy")
    test_coverage = component_doc.get("test_coverage", component_doc.get("test_coverage_percentage", 0))
    compliance_status = component_doc.get("compliance_status", "I1_I2_I3_I4_compliant")
    related_techniques = _ensure_list(component_doc.get("related_techniques", []))
    known_issues = _ensure_list(component_doc.get("known_issues", []))
    performance_metrics = component_doc.get("performance_metrics", {})
    complexity_score = component_doc.get("complexity_score", 1)

    rel_path = _relative_path(component_path, workspace_root)

    return {
        "component_id": component_id,
        "component_name": component_name,
        "component_type": component_type,
        "file_path": rel_path,
        "documentation_path": rel_path,
        "dependencies": dependencies,
        "dependents": dependents,
        "creation_timestamp": creation_timestamp,
        "last_modified_timestamp": last_modified_timestamp,
        "health_status": health_status,
        "test_coverage_percentage": test_coverage,
        "compliance_status": compliance_status,
        "performance_metrics": performance_metrics,
        "related_techniques": related_techniques,
        "known_issues": known_issues,
        "complexity_score": complexity_score,
    }


def _relative_path(path: Path, workspace_root: Optional[Path]) -> str:
    resolved_path = path.resolve()
    base = (workspace_root or Path(__file__).resolve().parents[2]).resolve()
    try:
        return resolved_path.relative_to(base).as_posix()
    except ValueError:
        return resolved_path.as_posix()


def _require(data: ComponentDoc, key: str) -> Any:
    if key not in data:
        raise ValueError(f"component document missing required field: {key}")
    return data[key]


def _ensure_list(values: Any) -> list[Any]:
    if values is None:
        return []
    if isinstance(values, list):
        return values
    if isinstance(values, Iterable) and not isinstance(values, (str, bytes)):
        return list(values)
    return [values]


def _load_json(path: Path) -> Dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Register a component documentation file into the component index.")
    parser.add_argument("--component", required=True, help="Path to the component JSON file")
    parser.add_argument(
        "--index",
        default="ai_docs/component_index.json",
        help="Path to the component index JSON file (default: ai_docs/component_index.json)",
    )
    parser.add_argument(
        "--workspace-root",
        default=None,
        help="Optional workspace root to compute relative paths (defaults to repository root)",
    )
    args = parser.parse_args(argv)

    component_path = Path(args.component)
    index_path = Path(args.index)
    workspace_root = Path(args.workspace_root).resolve() if args.workspace_root else None

    register_component(component_path, index_path, workspace_root)


if __name__ == "__main__":
    main()
