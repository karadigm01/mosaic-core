"""Synchronize component index entries with coverage reports."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple


@dataclass
class CoverageUpdate:
    """Record of a single component coverage update."""

    component_id: str
    file_path: str
    percent_covered: float


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_json(path: Path) -> Dict[str, object]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, payload: Dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _normalize_path(path: str | Path) -> str:
    return str(Path(path).resolve())


def _coverage_map(coverage_json: Path) -> Dict[str, float]:
    data = _load_json(coverage_json)
    files = data.get("files", {})
    coverage: Dict[str, float] = {}
    for file_path, stats in files.items():
        summary = stats.get("summary", {})
        percent = summary.get("percent_covered")
        if percent is None:
            continue
        coverage[_normalize_path(file_path)] = float(percent)
    return coverage


def _governance_coverage_map(workspace_root: Path) -> Dict[str, float]:
    """Return coverage percentages for governance artifacts recorded by schema tests."""

    coverage: Dict[str, float] = {}
    coverage_file = workspace_root / "logs" / "governance-coverage.json"
    if not coverage_file.exists():
        return coverage

    payload = _load_json(coverage_file)
    coverage_entries = payload.get("coverage")
    if isinstance(coverage_entries, dict):
        for rel_path, percent in coverage_entries.items():
            coverage[_normalize_path(workspace_root / rel_path)] = float(percent)

    files_section = payload.get("files")
    if isinstance(files_section, list):
        for rel_path in files_section:
            coverage.setdefault(_normalize_path(workspace_root / rel_path), 100.0)

    return coverage


def update_component_index_from_coverage(
    coverage_json_path: Path,
    component_index_path: Path,
    workspace_root: Path,
) -> List[CoverageUpdate]:
    """Update component coverage percentages using a coverage.py JSON report."""

    coverage_by_path = _coverage_map(coverage_json_path)
    coverage_by_path.update(_governance_coverage_map(workspace_root))
    index_payload = _load_json(component_index_path)
    components: List[dict] = index_payload.get("components", [])
    updates: List[CoverageUpdate] = []

    root = workspace_root.resolve()
    for component in components:
        rel_path = component.get("file_path")
        if not rel_path:
            continue
        abs_path = _normalize_path(root / rel_path)
        percent = coverage_by_path.get(abs_path)
        if percent is None:
            continue
        percent_value = round(percent, 2)
        if component.get("test_coverage_percentage") == percent_value:
            continue
        component["test_coverage_percentage"] = percent_value
        updates.append(
            CoverageUpdate(
                component_id=component.get("component_id", rel_path),
                file_path=rel_path,
                percent_covered=percent_value,
            )
        )

    if updates:
        metadata = index_payload.setdefault("metadata", {})
        metadata["last_updated"] = _utc_timestamp()
        _write_json(component_index_path, index_payload)

    return updates


__all__ = ["CoverageUpdate", "update_component_index_from_coverage"]
