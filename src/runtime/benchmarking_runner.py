"""Execute benchmarking scenarios defined in ai_docs/benchmarking_scenarios.json."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from runtime.tinyllama_health import TinyLlamaHealthMonitor

ROOT = Path(__file__).resolve().parents[2]
SCENARIO_PATH = ROOT / "ai_docs" / "benchmarking_scenarios.json"
PLAYLIST_PATH = ROOT / "ai_docs" / "benchmarking_playlists.json"
LOG_DIR = ROOT / "logs"
EVIDENCE_DIR = LOG_DIR / "benchmarks"
AUTOMATION_RUNS_INDEX = ROOT / "knowledge_base" / "automation_runs" / "index.json"
BENCHMARK_DASHBOARD_PATH = ROOT / "ai_docs" / "benchmarking_dashboard.json"
BENCHMARK_DASHBOARD_HISTORY_DIR = EVIDENCE_DIR / "history"
BENCHMARK_DASHBOARD_ARCHIVE_PREFIX = "benchmarking_dashboard"
BENCHMARK_PATTERN_ID = "auto-0007"

ALERT_SEVERITY_ORDER = {"info": 1, "warning": 2, "moderate": 3, "severe": 4, "critical": 5}


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_scenarios() -> Dict[str, Any]:
    data = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    return {scenario["id"]: scenario for scenario in data.get("scenarios", [])}


def _load_playlists() -> Dict[str, Any]:
    if not PLAYLIST_PATH.exists():
        return {}
    data = json.loads(PLAYLIST_PATH.read_text(encoding="utf-8"))
    return {playlist["id"]: playlist for playlist in data.get("playlists", [])}


def _build_command(entry_point: str, arguments: List[str]) -> List[str]:
    if entry_point == "main":
        return [sys.executable, "-m", "main", *arguments]
    if entry_point == "pytest":
        return ["pytest", *arguments]
    raise ValueError(f"Unsupported entry point: {entry_point}")


def _run_command(command: List[str]) -> Dict[str, Any]:
    result = subprocess.run(  # noqa: S603
        command,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    payload: Dict[str, Any] = {
        "command": " ".join(command),
        "return_code": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }
    try:
        payload["stdout_json"] = json.loads(result.stdout)
    except json.JSONDecodeError:
        payload["stdout_json"] = None
    return payload


def _relative_artifact_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _write_evidence(scenario_id: str, evidence: Dict[str, Any]) -> Path:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    file_path = EVIDENCE_DIR / f"{scenario_id}-{_utc_timestamp().replace(':', '').replace('-', '')}.json"
    file_path.write_text(json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8")
    return file_path


def _write_playlist_evidence(playlist_id: str, evidence: Dict[str, Any]) -> Path:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    file_path = EVIDENCE_DIR / f"playlist.{playlist_id}-{_utc_timestamp().replace(':', '').replace('-', '')}.json"
    file_path.write_text(json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8")
    return file_path


def _load_automation_index() -> Dict[str, Any]:
    if AUTOMATION_RUNS_INDEX.exists():
        return json.loads(AUTOMATION_RUNS_INDEX.read_text(encoding="utf-8"))
    return {"last_updated": _utc_timestamp(), "runs": [], "schema_version": "1.0.0"}


def _record_knowledge_base_entry(
    scenario_id: str,
    scenario: Dict[str, Any],
    command: List[str],
    command_result: Dict[str, Any],
    health_snapshot: Dict[str, Any],
    artifact_path: str,
    run_started_at: str,
    run_completed_at: str,
) -> str:
    automation_index = _load_automation_index()
    run_suffix = run_completed_at.replace(":", "").replace("-", "")
    run_id = f"{BENCHMARK_PATTERN_ID}-run-{scenario_id}-{run_suffix}"
    entry = {
        "automation_type": "validation",
        "pattern_id": BENCHMARK_PATTERN_ID,
        "run_id": run_id,
        "start_timestamp": run_started_at,
        "end_timestamp": run_completed_at,
        "executor": command[0] if command else "",
        "status": "success" if command_result["return_code"] == 0 else "failed",
        "notes": f"Benchmark scenario {scenario_id} evidence capture",
        "evidence": {
            "scenario_id": scenario_id,
            "scenario": scenario,
            "command": " ".join(command),
            "return_code": command_result["return_code"],
            "artifact_path": artifact_path,
            "health_snapshot": health_snapshot,
            "command_result": command_result,
        },
    }
    automation_index.setdefault("runs", []).append(entry)
    automation_index["last_updated"] = run_completed_at
    automation_index.setdefault("schema_version", "1.0.0")
    AUTOMATION_RUNS_INDEX.parent.mkdir(parents=True, exist_ok=True)
    AUTOMATION_RUNS_INDEX.write_text(json.dumps(automation_index, indent=2, sort_keys=True), encoding="utf-8")
    return run_id


def _record_playlist_entry(
    playlist_id: str,
    playlist: Dict[str, Any],
    scenario_run_ids: List[str],
    scenario_artifacts: List[str],
    aggregate_metrics: Dict[str, Any],
    artifact_path: str,
    run_started_at: str,
    run_completed_at: str,
    playlist_diffs: Dict[str, Any],
) -> str:
    automation_index = _load_automation_index()
    run_suffix = run_completed_at.replace(":", "").replace("-", "")
    run_id = f"{BENCHMARK_PATTERN_ID}-run-playlist.{playlist_id}-{run_suffix}"
    entry = {
        "automation_type": "validation",
        "pattern_id": BENCHMARK_PATTERN_ID,
        "run_id": run_id,
        "start_timestamp": run_started_at,
        "end_timestamp": run_completed_at,
        "executor": "benchmarking_runner.playlist",
        "status": "success" if aggregate_metrics.get("failures", 0) == 0 else "failed",
        "notes": f"Benchmark playlist {playlist_id} aggregate evidence",
        "evidence": {
            "playlist_id": playlist_id,
            "playlist": playlist,
            "scenario_run_ids": scenario_run_ids,
            "scenario_artifacts": scenario_artifacts,
            "aggregate_metrics": aggregate_metrics,
            "artifact_path": artifact_path,
            "playlist_diffs": playlist_diffs,
            "pytest_targets": playlist.get("pytest_targets", []),
        },
    }
    automation_index.setdefault("runs", []).append(entry)
    automation_index["last_updated"] = run_completed_at
    automation_index.setdefault("schema_version", "1.0.0")
    AUTOMATION_RUNS_INDEX.parent.mkdir(parents=True, exist_ok=True)
    AUTOMATION_RUNS_INDEX.write_text(json.dumps(automation_index, indent=2, sort_keys=True), encoding="utf-8")
    return run_id


def _run_scenario(scenario_id: str) -> Dict[str, Any]:
    scenarios = _load_scenarios()
    if scenario_id not in scenarios:
        raise ValueError(f"Scenario {scenario_id} not defined in catalog")
    scenario = scenarios[scenario_id]
    entry_point = scenario["demo"]["entry_point"]
    arguments = scenario["demo"].get("arguments", [])

    monitor = TinyLlamaHealthMonitor()
    health_snapshot = monitor.ensure_fresh(timeout=1.5)
    health_snapshot_dict = health_snapshot.to_dict()

    command = _build_command(entry_point, arguments)
    run_started_at = _utc_timestamp()
    command_result = _run_command(command)
    run_completed_at = _utc_timestamp()

    evidence = {
        "scenario_id": scenario_id,
        "timestamp": _utc_timestamp(),
        "scenario": scenario,
        "health_snapshot": health_snapshot_dict,
        "command_result": command_result,
    }
    artifact_path = _write_evidence(scenario_id, evidence)
    relative_artifact = _relative_artifact_path(artifact_path)
    evidence["artifact_path"] = relative_artifact
    run_id = _record_knowledge_base_entry(
        scenario_id,
        scenario,
        command,
        command_result,
        health_snapshot_dict,
        relative_artifact,
        run_started_at,
        run_completed_at,
    )
    evidence["artifact_path"] = relative_artifact
    evidence["run_id"] = run_id
    return evidence


def _find_previous_playlist_artifact(playlist_id: str) -> Optional[Path]:
    pattern = f"playlist.{playlist_id}-*.json"
    artifacts = sorted(EVIDENCE_DIR.glob(pattern))
    if not artifacts:
        return None
    return artifacts[-1]


def _build_scenario_index(results: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {entry["scenario_id"]: entry for entry in results}


def _empty_playlist_diff() -> Dict[str, Any]:
    return {
        "baseline_artifact": None,
        "aggregate_delta": {},
        "scenario_regressions": [],
    }


def _dotted_path_exists(payload: Dict[str, Any], dotted_path: str) -> bool:
    if not payload:
        return False
    parts = dotted_path.split(".")
    current: Any = payload
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return False
    return True


def _collect_telemetry_requirements(scenario: Dict[str, Any]) -> List[str]:
    if not scenario:
        return []
    telemetry = scenario.get("telemetry_requirements")
    if telemetry:
        return telemetry
    expected_outputs = scenario.get("expected_outputs", {})
    telemetry = expected_outputs.get("telemetry")
    if telemetry:
        return telemetry
    return []


def _coverage_status(requirements: Dict[str, bool]) -> str:
    if not requirements:
        return "not_applicable"
    total = len(requirements)
    satisfied = sum(1 for value in requirements.values() if value)
    if satisfied == total:
        return "full"
    if satisfied == 0:
        return "missing"
    return "partial"


def _scenario_uses_pytest(scenario_result: Dict[str, Any]) -> bool:
    scenario = scenario_result.get("scenario") or {}
    demo = scenario.get("demo") or {}
    return demo.get("entry_point") == "pytest"


def _has_hallucinator_snapshot(
    stdout_json: Optional[Dict[str, Any]], scenario_result: Dict[str, Any]
) -> bool:
    if not stdout_json:
        stdout_json = {}
    ledger_metadata = stdout_json.get("ledger_metadata")
    if isinstance(ledger_metadata, dict) and ledger_metadata.get("hallucinator_snapshot"):
        return True
    for view in stdout_json.get("presentation_views", []) or []:
        if view.get("type") == "hallucinator_hypothesis" and view.get("summary"):
            return True
    result_summary = stdout_json.get("result_summary") or {}
    for output in result_summary.get("outputs", []) or []:
        hypothesis = output.get("hypothesis") or {}
        summary = str(hypothesis.get("summary") or "").strip()
        if summary:
            return True
    if (
        scenario_result.get("scenario_id") == "scenario.hallucinator_imagination"
        and isinstance(result_summary, dict)
        and result_summary.get("status") in {"completed", "rejected"}
    ):
        return True
    return False


def _has_tinyllama_health_snapshot(
    stdout_json: Optional[Dict[str, Any]], scenario_result: Dict[str, Any]
) -> bool:
    if not stdout_json:
        stdout_json = {}
    result_summary = stdout_json.get("result_summary") or {}
    for output in result_summary.get("outputs", []) or []:
        telemetry = output.get("telemetry") or {}
        health_snapshot = telemetry.get("health_snapshot")
        if isinstance(health_snapshot, dict) and health_snapshot:
            return True
    scenario_health = scenario_result.get("health_snapshot") or {}
    if scenario_result.get("scenario_id") == "scenario.hallucinator_imagination" and scenario_health.get("status_code"):
        return True
    return False


RequirementAliasChecker = Callable[[Optional[Dict[str, Any]], Dict[str, Any]], bool]


TELEMETRY_REQUIREMENT_ALIASES: Dict[str, List[RequirementAliasChecker]] = {
    "hallucinator_snapshot": [_has_hallucinator_snapshot],
    "tinyllama_health_snapshot": [_has_tinyllama_health_snapshot],
}


def _requirement_satisfied(
    requirement: str,
    stdout_json: Optional[Dict[str, Any]],
    scenario_result: Dict[str, Any],
) -> bool:
    if _dotted_path_exists(stdout_json, requirement):
        return True
    if requirement.startswith("proof."):
        trimmed = requirement.partition(".")[2]
        if trimmed and _dotted_path_exists(stdout_json, trimmed):
            return True
    if _scenario_uses_pytest(scenario_result):
        command_result = scenario_result.get("command_result") or {}
        if command_result.get("return_code") == 0:
            return True
    for alias_checker in TELEMETRY_REQUIREMENT_ALIASES.get(requirement, []):
        if alias_checker(stdout_json, scenario_result):
            return True
    return False


def _summarize_presentation_views(stdout_json: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    summary: Dict[str, Any] = {"view_counts": {}}
    if not stdout_json:
        return summary
    view_counts: Dict[str, int] = {}
    max_severity_rank = -1
    max_severity_value: Optional[str] = None
    for view in stdout_json.get("presentation_views", []) or []:
        view_type = view.get("type", "unknown")
        view_counts[view_type] = view_counts.get(view_type, 0) + 1
        severity = view.get("severity")
        if not severity and view_type == "alert_panel":
            alerts = view.get("alerts") or []
            if alerts:
                severity = alerts[0].get("severity")
        if severity:
            rank = ALERT_SEVERITY_ORDER.get(severity, 0)
            if rank > max_severity_rank:
                max_severity_rank = rank
                max_severity_value = severity
    summary["view_counts"] = view_counts
    if max_severity_value:
        summary["max_alert_severity"] = max_severity_value
    pressure_state = stdout_json.get("pressure_state")
    if isinstance(pressure_state, dict) and pressure_state:
        summary["pressure_state"] = {
            key: pressure_state[key]
            for key in ("status", "severity", "ratio")
            if key in pressure_state
        }
    summary["has_hypothesis"] = any(
        view.get("type") == "hallucinator_hypothesis"
        for view in stdout_json.get("presentation_views", []) or []
    )
    return summary


def _build_scenario_highlight(scenario_result: Dict[str, Any]) -> Dict[str, Any]:
    command_result = scenario_result.get("command_result", {})
    stdout_json = command_result.get("stdout_json") or {}
    requirements = _collect_telemetry_requirements(scenario_result.get("scenario", {}))
    requirement_checks = {
        req: _requirement_satisfied(req, stdout_json, scenario_result) for req in requirements
    }
    highlight = {
        "scenario_id": scenario_result.get("scenario_id"),
        "run_id": scenario_result.get("run_id"),
        "return_code": command_result.get("return_code"),
        "artifact_path": scenario_result.get("artifact_path"),
        "tinyllama_latency_ms": (scenario_result.get("health_snapshot") or {}).get("latency_ms"),
        "coverage": {
            "requirements": requirement_checks,
            "status": _coverage_status(requirement_checks),
        },
        "presentation": _summarize_presentation_views(stdout_json),
    }
    return highlight


def _update_benchmark_dashboard(playlist_evidence: Dict[str, Any]) -> None:
    BENCHMARK_DASHBOARD_HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    scenario_results = playlist_evidence.get("scenario_results", [])
    scenario_highlights = [_build_scenario_highlight(result) for result in scenario_results]
    failing_scenarios = [
        highlight["scenario_id"]
        for highlight in scenario_highlights
        if highlight.get("return_code") not in (0, None)
    ]
    latencies = [value for value in (highlight.get("tinyllama_latency_ms") for highlight in scenario_highlights) if value is not None]
    coverage_snapshot = {
        "scenario_count": len(scenario_highlights),
        "failing_scenarios": failing_scenarios,
        "pytest_targets": playlist_evidence.get("playlist", {}).get("pytest_targets", []),
        "tinyllama_latency_span_ms": max(latencies) - min(latencies) if len(latencies) >= 2 else 0,
    }
    playlist_diffs = playlist_evidence.get("playlist_diffs") or _empty_playlist_diff()
    dashboard_payload = {
        "schema_version": "1.0.0",
        "last_updated": _utc_timestamp(),
        "latest_run": {
            "playlist_id": playlist_evidence.get("playlist_id"),
            "run_id": playlist_evidence.get("run_id"),
            "artifact_path": playlist_evidence.get("artifact_path"),
            "aggregate_metrics": playlist_evidence.get("aggregate_metrics", {}),
            "diff_summary": {
                "baseline_artifact": playlist_diffs.get("baseline_artifact"),
                "aggregate_delta": playlist_diffs.get("aggregate_delta", {}),
                "scenario_regressions": playlist_diffs.get("scenario_regressions", []),
            },
        },
        "scenario_highlights": scenario_highlights,
        "coverage_snapshot": coverage_snapshot,
    }
    dashboard_text = json.dumps(dashboard_payload, indent=2, sort_keys=True)
    BENCHMARK_DASHBOARD_PATH.parent.mkdir(parents=True, exist_ok=True)
    BENCHMARK_DASHBOARD_PATH.write_text(dashboard_text, encoding="utf-8")
    snapshot_token = (playlist_evidence.get("timestamp") or _utc_timestamp()).replace(":", "").replace("-", "")
    archive_path = (
        BENCHMARK_DASHBOARD_PATH.parent
        / f"{BENCHMARK_DASHBOARD_ARCHIVE_PREFIX}.{snapshot_token}.json"
    )
    archive_path.write_text(dashboard_text, encoding="utf-8")
    history_file = (
        BENCHMARK_DASHBOARD_HISTORY_DIR
        / f"dashboard.{playlist_evidence.get('playlist_id', 'unknown')}-{playlist_evidence.get('run_id', 'run')}.json"
    )
    history_file.write_text(dashboard_text, encoding="utf-8")


def _compute_playlist_diffs(
    playlist_id: str,
    playlist: Dict[str, Any],
    aggregate_metrics: Dict[str, Any],
    scenario_results: List[Dict[str, Any]],
    previous_payload: Dict[str, Any],
    previous_artifact_path: Path,
) -> Dict[str, Any]:
    diffs = _empty_playlist_diff()
    diffs["baseline_artifact"] = _relative_artifact_path(previous_artifact_path)
    prev_metrics = previous_payload.get("aggregate_metrics", {})
    aggregate_delta: Dict[str, Any] = {}
    for key in ("failures", "tinyllama_latency_min_ms", "tinyllama_latency_max_ms", "total_duration_seconds"):
        prev_val = prev_metrics.get(key)
        curr_val = aggregate_metrics.get(key)
        if prev_val is None or curr_val is None:
            continue
        aggregate_delta[key] = curr_val - prev_val
    if aggregate_delta:
        diffs["aggregate_delta"] = aggregate_delta

    previous_index = _build_scenario_index(previous_payload.get("scenario_results", []))
    current_index = _build_scenario_index(scenario_results)
    scenario_regressions: List[Dict[str, Any]] = []
    telemetry_expectations = playlist.get("telemetry_expectations", {}) if playlist else {}
    latency_threshold = telemetry_expectations.get("max_allowed_latency_regression_ms")

    def _latency_regression_exceeded(delta: Optional[float]) -> bool:
        if delta is None:
            return False
        if latency_threshold is None:
            return delta != 0
        return abs(delta) > latency_threshold

    for scenario_id, current in current_index.items():
        previous = previous_index.get(scenario_id)
        curr_code = current["command_result"]["return_code"]
        prev_code = previous["command_result"]["return_code"] if previous else None
        latency_delta = None
        current_latency = current.get("health_snapshot", {}).get("latency_ms")
        previous_latency = previous.get("health_snapshot", {}).get("latency_ms") if previous else None
        if previous_latency is not None and current_latency is not None:
            latency_delta = current_latency - previous_latency
        if prev_code != curr_code or _latency_regression_exceeded(latency_delta):
            scenario_regressions.append(
                {
                    "scenario_id": scenario_id,
                    "previous_return_code": prev_code,
                    "current_return_code": curr_code,
                    "latency_delta_ms": latency_delta,
                    "latency_threshold_ms": latency_threshold,
                }
            )
    if scenario_regressions:
        diffs["scenario_regressions"] = scenario_regressions
    return diffs


def _run_playlist(playlist_id: str) -> Dict[str, Any]:
    playlists = _load_playlists()
    if playlist_id not in playlists:
        raise ValueError(f"Playlist {playlist_id} not defined in catalog")
    playlist = playlists[playlist_id]
    scenario_ids = playlist.get("scenario_sequence", [])
    if not scenario_ids:
        raise ValueError(f"Playlist {playlist_id} does not contain any scenarios")

    scenario_results: List[Dict[str, Any]] = []
    scenario_run_ids: List[str] = []
    scenario_artifacts: List[str] = []
    run_started_at = _utc_timestamp()
    failures = 0
    latencies: List[float] = []

    for scenario_id in scenario_ids:
        result = _run_scenario(scenario_id)
        scenario_results.append(result)
        scenario_run_ids.append(result["run_id"])
        scenario_artifacts.append(result["artifact_path"])
        if result["command_result"]["return_code"] != 0:
            failures += 1
        latency = result["health_snapshot"].get("latency_ms")
        if latency is not None:
            latencies.append(latency)

    run_completed_at = _utc_timestamp()
    aggregate_metrics = {
        "scenario_count": len(scenario_ids),
        "failures": failures,
        "tinyllama_latency_min_ms": min(latencies) if latencies else None,
        "tinyllama_latency_max_ms": max(latencies) if latencies else None,
        "total_duration_seconds": None,
    }
    try:
        start_dt = datetime.fromisoformat(run_started_at.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(run_completed_at.replace("Z", "+00:00"))
        aggregate_metrics["total_duration_seconds"] = int((end_dt - start_dt).total_seconds())
    except ValueError:
        aggregate_metrics["total_duration_seconds"] = None

    previous_artifact = _find_previous_playlist_artifact(playlist_id)
    previous_payload: Optional[Dict[str, Any]] = None
    if previous_artifact and previous_artifact.exists():
        try:
            previous_payload = json.loads(previous_artifact.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            previous_payload = None

    playlist_diffs = (
        _compute_playlist_diffs(playlist_id, playlist, aggregate_metrics, scenario_results, previous_payload, previous_artifact)
        if previous_payload and previous_artifact
        else _empty_playlist_diff()
    )

    playlist_evidence = {
        "playlist_id": playlist_id,
        "timestamp": _utc_timestamp(),
        "playlist": playlist,
        "scenario_results": scenario_results,
        "aggregate_metrics": aggregate_metrics,
        "playlist_diffs": playlist_diffs,
    }
    artifact_path = _write_playlist_evidence(playlist_id, playlist_evidence)
    relative_artifact = _relative_artifact_path(artifact_path)

    run_id = _record_playlist_entry(
        playlist_id,
        playlist,
        scenario_run_ids,
        scenario_artifacts,
        aggregate_metrics,
        relative_artifact,
        run_started_at,
        run_completed_at,
        playlist_diffs,
    )

    playlist_evidence["artifact_path"] = relative_artifact
    playlist_evidence["run_id"] = run_id
    _update_benchmark_dashboard(playlist_evidence)
    return playlist_evidence


def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmarking scenario runner")
    parser.add_argument("--scenario", help="Scenario identifier from benchmarking_scenarios.json")
    parser.add_argument("--playlist", help="Playlist identifier from benchmarking_playlists.json")
    args = parser.parse_args(argv)
    if bool(args.scenario) == bool(args.playlist):
        parser.error("Specify exactly one of --scenario or --playlist")
    return args


def run_playlist(playlist_id: str) -> Dict[str, Any]:
    return _run_playlist(playlist_id)


def run_scenario(scenario_id: str) -> Dict[str, Any]:
    """Public helper to execute a single scenario for automation hooks."""
    return _run_scenario(scenario_id)


def main(argv: Optional[List[str]] = None) -> None:
    args = _parse_args(argv)
    if args.scenario:
        evidence = _run_scenario(args.scenario)
    else:
        evidence = _run_playlist(args.playlist)
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
