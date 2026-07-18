"""Automation helpers for keeping governance JSON artifacts in sync."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List

ComponentIndex = Dict[str, Any]
ComponentEntry = Dict[str, Any]


def ensure_component_registration(index_data: ComponentIndex, component_entry: ComponentEntry) -> ComponentIndex:
    """Insert or update a component entry while preserving deterministic order."""
    updated = deepcopy(index_data)
    components: List[ComponentEntry] = updated.setdefault("components", [])
    for idx, existing in enumerate(components):
        if existing.get("component_id") == component_entry.get("component_id"):
            components[idx] = {**existing, **component_entry}
            break
    else:
        components.append(component_entry)
        components.sort(key=lambda item: item.get("component_id", ""))
    _recompute_metadata(updated)
    return updated


def detect_missing_components(index_data: ComponentIndex, expected_ids: List[str]) -> List[str]:
    """Return component IDs that are not registered in the index."""
    registered = {component.get("component_id") for component in index_data.get("components", [])}
    return sorted(set(expected_ids) - registered)


def _recompute_metadata(index_data: ComponentIndex) -> None:
    components = index_data.get("components", [])
    metadata = index_data.setdefault("metadata", {})
    health = index_data.setdefault("health_status", {})
    metadata["total_components"] = len(components)
    health_counts = {"healthy": 0, "degraded": 0, "failing": 0}
    for component in components:
        state = component.get("health_status", "healthy")
        if state not in health_counts:
            state = "degraded"
        health_counts[state] += 1
    health["total_healthy"] = health_counts["healthy"]
    health["total_degraded"] = health_counts["degraded"]
    health["total_failing"] = health_counts["failing"]
