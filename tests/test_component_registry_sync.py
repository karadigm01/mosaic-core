from __future__ import annotations

import json
from pathlib import Path

from runtime.component_registry_sync import build_component_entry, register_component


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_register_component_adds_entry(tmp_path: Path) -> None:
    workspace_root = tmp_path
    component_path = workspace_root / "ai_docs" / "demo_component.json"
    index_path = workspace_root / "ai_docs" / "component_index.json"

    component_doc = {
        "component_id": "demo_component",
        "component_name": "Demo Component",
        "component_type": "runtime_module",
        "creation_timestamp": "2026-01-19T00:00:00Z",
        "last_modified_timestamp": "2026-01-19T00:00:00Z",
        "dependencies": ["substrate_contracts"],
        "related_techniques": ["tech-0008"],
    }
    _write_json(component_path, component_doc)

    index_seed = {
        "components": [],
        "metadata": {"total_components": 0},
        "health_status": {"total_healthy": 0, "total_degraded": 0, "total_failing": 0},
    }
    _write_json(index_path, index_seed)

    register_component(component_path, index_path, workspace_root)

    updated = json.loads(index_path.read_text(encoding="utf-8"))
    assert updated["metadata"]["total_components"] == 1
    assert updated["health_status"]["total_healthy"] == 1
    entry = updated["components"][0]
    assert entry["component_id"] == "demo_component"
    assert entry["file_path"] == "ai_docs/demo_component.json"
    assert entry["test_coverage_percentage"] == 0


def test_register_component_updates_existing_entry(tmp_path: Path) -> None:
    workspace_root = tmp_path
    component_path = workspace_root / "ai_docs" / "demo_component.json"
    index_path = workspace_root / "ai_docs" / "component_index.json"

    component_doc = {
        "component_id": "demo_component",
        "component_name": "Demo Component",
        "component_type": "runtime_module",
        "creation_timestamp": "2026-01-19T00:00:00Z",
        "last_modified_timestamp": "2026-01-19T00:05:00Z",
        "dependencies": [],
        "health_status": "healthy",
        "test_coverage": 85,
        "related_techniques": ["tech-0008"],
    }
    _write_json(component_path, component_doc)

    existing_entry = {
        "component_id": "demo_component",
        "component_name": "Old Name",
        "component_type": "runtime_module",
        "file_path": "ai_docs/demo_component.json",
        "documentation_path": "ai_docs/demo_component.json",
        "dependencies": [],
        "dependents": [],
        "creation_timestamp": "2026-01-19T00:00:00Z",
        "last_modified_timestamp": "2026-01-19T00:00:00Z",
        "health_status": "healthy",
        "test_coverage_percentage": 50,
        "compliance_status": "I1_I2_I3_I4_compliant",
        "performance_metrics": {},
        "related_techniques": [],
        "known_issues": [],
        "complexity_score": 1,
    }
    index_seed = {
        "components": [existing_entry],
        "metadata": {"total_components": 1},
        "health_status": {"total_healthy": 1, "total_degraded": 0, "total_failing": 0},
    }
    _write_json(index_path, index_seed)

    register_component(component_path, index_path, workspace_root)

    updated = json.loads(index_path.read_text(encoding="utf-8"))
    assert updated["metadata"]["total_components"] == 1
    entry = updated["components"][0]
    assert entry["component_name"] == "Demo Component"
    assert entry["test_coverage_percentage"] == 85
    assert entry["last_modified_timestamp"] == "2026-01-19T00:05:00Z"


def test_build_component_entry_defaults(tmp_path: Path) -> None:
    component_doc = {
        "component_id": "demo_component",
        "component_name": "Demo Component",
        "component_type": "runtime_module",
    }
    component_path = tmp_path / "demo_component.json"
    component_path.write_text(json.dumps(component_doc), encoding="utf-8")

    entry = build_component_entry(component_doc, component_path, tmp_path)

    assert entry["dependencies"] == []
    assert entry["health_status"] == "healthy"
    assert entry["test_coverage_percentage"] == 0
    assert entry["compliance_status"] == "I1_I2_I3_I4_compliant"
    assert entry["file_path"].endswith("demo_component.json")
