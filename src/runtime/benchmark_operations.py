"""Record benchmarking replay and remediation operations."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
OPERATIONS_DIR = ROOT / "logs" / "benchmarks"
REPLAY_LOG_PATH = OPERATIONS_DIR / "replay_events.json"
REMEDIATION_LOG_PATH = OPERATIONS_DIR / "remediation_events.json"


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_events(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def _write_events(path: Path, events: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(events, indent=2, sort_keys=True), encoding="utf-8")


def record_replay_event(
    scenario_id: str,
    run_id: Optional[str],
    artifact_path: Optional[str],
    return_code: Optional[int],
) -> Dict[str, Any]:
    events = _read_events(REPLAY_LOG_PATH)
    entry = {
        "id": str(uuid.uuid4()),
        "timestamp": _utc_timestamp(),
        "scenario_id": scenario_id,
        "run_id": run_id,
        "artifact_path": artifact_path,
        "return_code": return_code,
    }
    events.append(entry)
    _write_events(REPLAY_LOG_PATH, events)
    return entry


def record_remediation_event(
    scenario_id: str,
    action: str,
    status: str,
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    events = _read_events(REMEDIATION_LOG_PATH)
    entry = {
        "id": str(uuid.uuid4()),
        "timestamp": _utc_timestamp(),
        "scenario_id": scenario_id,
        "action": action,
        "status": status,
        "details": details or {},
    }
    events.append(entry)
    _write_events(REMEDIATION_LOG_PATH, events)
    return entry


def _count_backlog(remediation_events: List[Dict[str, Any]]) -> int:
    backlog_statuses = {"open", "needs_follow_up"}
    return sum(1 for event in remediation_events if event.get("status") in backlog_statuses)


def load_summary(limit: int = 8) -> Dict[str, Any]:
    replay_events = _read_events(REPLAY_LOG_PATH)
    remediation_events = _read_events(REMEDIATION_LOG_PATH)
    summary = {
        "replay_count": len(replay_events),
        "last_replay_timestamp": replay_events[-1]["timestamp"] if replay_events else None,
        "remediation_backlog": _count_backlog(remediation_events),
        "remediation_total": len(remediation_events),
        "recent_replays": replay_events[-limit:],
        "recent_remediations": remediation_events[-limit:],
    }
    return summary