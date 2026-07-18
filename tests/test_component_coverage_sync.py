from __future__ import annotations

import json
from pathlib import Path

from runtime.component_coverage_sync import CoverageUpdate, update_component_index_from_coverage


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_update_component_index_from_coverage_updates_matching_entries(tmp_path: Path) -> None:
    workspace_root = tmp_path
    component_index = workspace_root / "ai_docs" / "component_index.json"
    coverage_json = workspace_root / "logs" / "coverage.json"
    source_file = workspace_root / "src" / "runtime" / "tile.py"

    index_payload = {
        "components": [
            {
                "component_id": "tile",
                "component_name": "Tile",
                "component_type": "runtime_module",
                "file_path": "src/runtime/tile.py",
                "test_coverage_percentage": 0,
            }
        ],
        "metadata": {"last_updated": "2026-01-01T00:00:00Z"},
    }
    coverage_payload = {
        "files": {
            str(source_file): {
                "executed_lines": [1, 2],
                "missing_lines": [],
                "summary": {"percent_covered": 87.5},
            }
        }
    }

    _write_json(component_index, index_payload)
    _write_json(coverage_json, coverage_payload)

    updates = update_component_index_from_coverage(coverage_json, component_index, workspace_root)

    assert updates == [CoverageUpdate(component_id="tile", file_path="src/runtime/tile.py", percent_covered=87.5)]
    updated_index = json.loads(component_index.read_text(encoding="utf-8"))
    assert updated_index["components"][0]["test_coverage_percentage"] == 87.5
    assert updated_index["metadata"]["last_updated"] != "2026-01-01T00:00:00Z"


def test_update_component_index_from_coverage_skips_missing_paths(tmp_path: Path) -> None:
    workspace_root = tmp_path
    component_index = workspace_root / "ai_docs" / "component_index.json"
    coverage_json = workspace_root / "logs" / "coverage.json"

    _write_json(
        component_index,
        {
            "components": [
                {
                    "component_id": "tile",
                    "component_name": "Tile",
                    "component_type": "runtime_module",
                    "file_path": "src/runtime/tile.py",
                    "test_coverage_percentage": 0,
                }
            ],
            "metadata": {"last_updated": "2026-01-01T00:00:00Z"},
        },
    )
    _write_json(coverage_json, {"files": {}})

    updates = update_component_index_from_coverage(coverage_json, component_index, workspace_root)

    assert updates == []
    untouched_index = json.loads(component_index.read_text(encoding="utf-8"))
    assert untouched_index["components"][0]["test_coverage_percentage"] == 0
    assert untouched_index["metadata"]["last_updated"] == "2026-01-01T00:00:00Z"
