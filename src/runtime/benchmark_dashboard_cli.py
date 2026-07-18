"""Render benchmarking dashboard summaries for governance reviewers."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from runtime import benchmark_operations

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DASHBOARD_PATH = ROOT / "ai_docs" / "benchmarking_dashboard.json"
DEFAULT_HISTORY_DIR = ROOT / "logs" / "benchmarks" / "history"
SYSTEM_STATUS_PATH = ROOT / "SYSTEM_STATUS.md"
DASHBOARD_BLOCK_START = "<!-- dashboard:begin -->"
DASHBOARD_BLOCK_END = "<!-- dashboard:end -->"
SYSTEM_SUMMARY_PATH = ROOT / "SYSTEM_SUMMARY.md"
SUMMARY_BLOCK_START = "<!-- dashboard-summary:begin -->"
SUMMARY_BLOCK_END = "<!-- dashboard-summary:end -->"

def _include_previous_snapshot() -> Optional[Path]:
    if not DEFAULT_HISTORY_DIR.exists():
        return None
    files = sorted(DEFAULT_HISTORY_DIR.glob("dashboard.*.json"))
    if len(files) < 2:
        return None
    return files[-2]


def _load_dashboard(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Dashboard file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _format_view_counts(view_counts: Dict[str, int]) -> str:
    if not view_counts:
        return "none"
    ordered = sorted(view_counts.items())
    return ", ".join(f"{name}:{count}" for name, count in ordered)


def _format_missing(requirements: Dict[str, bool]) -> str:
    missing = sorted(key for key, value in requirements.items() if not value)
    if not missing:
        return "none"
    return ", ".join(missing)


def render_dashboard(dashboard: Dict[str, Any]) -> str:
    latest = dashboard.get("latest_run", {})
    aggregate = latest.get("aggregate_metrics", {})
    diff_summary = latest.get("diff_summary", {})
    snapshot = dashboard.get("coverage_snapshot", {})

    lines: List[str] = []
    lines.append(
        f"Playlist {latest.get('playlist_id', 'n/a')} (run {latest.get('run_id', 'n/a')})"
    )
    lines.append(
        "Aggregate: "
        f"scenarios={aggregate.get('scenario_count', 0)} | "
        f"failures={aggregate.get('failures', 0)} | "
        f"tinyllama_latency_min={aggregate.get('tinyllama_latency_min_ms', 'n/a')}ms | "
        f"max={aggregate.get('tinyllama_latency_max_ms', 'n/a')}ms"
    )
    lines.append(
        "Coverage Snapshot: "
        f"scenario_count={snapshot.get('scenario_count', 0)}, "
        f"failures={len(snapshot.get('failing_scenarios', []))}, "
        f"pytest_targets={len(snapshot.get('pytest_targets', []))}, "
        f"latency_span_ms={snapshot.get('tinyllama_latency_span_ms', 'n/a')}"
    )
    lines.append(
        "Diff Summary: "
        f"baseline={diff_summary.get('baseline_artifact') or 'none'}, "
        f"aggregate_delta={diff_summary.get('aggregate_delta', {}) or '{}'}, "
        f"scenario_regressions={len(diff_summary.get('scenario_regressions', []))}"
    )

    lines.append("")
    lines.append("Scenario Highlights:")
    for highlight in dashboard.get("scenario_highlights", []):
        coverage = highlight.get("coverage", {})
        presentation = highlight.get("presentation", {})
        view_counts = presentation.get("view_counts", {})
        pressure_state = presentation.get("pressure_state", {})
        severity = presentation.get("max_alert_severity") or pressure_state.get("severity")
        lines.append(
            f"- {highlight.get('scenario_id')} (run {highlight.get('run_id')}): "
            f"return_code={highlight.get('return_code')} | "
            f"coverage={coverage.get('status', 'unknown')} (missing={_format_missing(coverage.get('requirements', {}))}) | "
            f"views={_format_view_counts(view_counts)} | "
            f"severity={severity or 'none'} | latency_ms={highlight.get('tinyllama_latency_ms', 'n/a')}"
        )
    regressions = diff_summary.get("scenario_regressions", [])
    if regressions:
        lines.append("")
        lines.append("Regressions:")
        for regression in regressions:
            lines.append(
                f"- {regression.get('scenario_id')}: "
                f"prev_code={regression.get('previous_return_code')} -> "
                f"curr_code={regression.get('current_return_code')} | "
                f"latency_delta_ms={regression.get('latency_delta_ms')}"
            )
    prev_path = _include_previous_snapshot()
    if prev_path:
        lines.append("")
        lines.append(f"Previous snapshot: {prev_path.relative_to(ROOT)}")
    return "\n".join(lines)


def _generate_system_status_block(dashboard: Dict[str, Any], operations: Optional[Dict[str, Any]] = None) -> str:
    latest = dashboard.get("latest_run", {})
    aggregate = latest.get("aggregate_metrics", {})
    snapshot = dashboard.get("coverage_snapshot", {})
    diff_summary = latest.get("diff_summary", {})
    operations = operations or {}

    latency_min = aggregate.get("tinyllama_latency_min_ms", "n/a")
    latency_max = aggregate.get("tinyllama_latency_max_ms", "n/a")
    playlist_id = latest.get("playlist_id", "n/a")
    run_id = latest.get("run_id", "n/a")
    artifact_path = latest.get("artifact_path", "n/a")

    lines: List[str] = ["### Benchmarking Dashboard Snapshot", ""]
    lines.append(
        "- "
        f"Playlist `{playlist_id}` run `{run_id}` captured {aggregate.get('scenario_count', 0)} scenarios "
        f"with {aggregate.get('failures', 0)} failures and TinyLLaMA latency {latency_min}–{latency_max} ms."
    )
    lines.append(
        "- "
        f"Coverage snapshot: scenarios={snapshot.get('scenario_count', 0)}, "
        f"failing={len(snapshot.get('failing_scenarios', []))}, "
        f"pytest_targets={len(snapshot.get('pytest_targets', []))}, "
        f"latency_span_ms={snapshot.get('tinyllama_latency_span_ms', 'n/a')}"
    )
    lines.append(
        "- "
        f"Diff baseline `{diff_summary.get('baseline_artifact') or 'none'}` with aggregate deltas "
        f"{diff_summary.get('aggregate_delta', {}) or '{}'}; artifact `{artifact_path}`."
    )
    lines.append("- Scenario Coverage Highlights:")
    for highlight in dashboard.get("scenario_highlights", []):
        coverage = highlight.get("coverage", {})
        presentation = highlight.get("presentation", {})
        pressure_state = presentation.get("pressure_state", {})
        severity = presentation.get("max_alert_severity") or pressure_state.get("severity") or "none"
        view_counts = _format_view_counts(presentation.get("view_counts", {}))
        missing = _format_missing(coverage.get("requirements", {}))
        lines.append(
            "  - "
            f"`{highlight.get('scenario_id')}` coverage **{coverage.get('status', 'unknown')}** "
            f"(missing: {missing}) | severity {severity} | latency_ms={highlight.get('tinyllama_latency_ms', 'n/a')} | views {view_counts}"
        )
    regressions = diff_summary.get("scenario_regressions", [])
    if regressions:
        lines.append("- Detected Regressions:")
        for regression in regressions:
            lines.append(
                "  - "
                f"`{regression.get('scenario_id')}` prev={regression.get('previous_return_code')} -> "
                f"curr={regression.get('current_return_code')} | latency_delta_ms={regression.get('latency_delta_ms')}"
            )
    prev_path = _include_previous_snapshot()
    if prev_path:
        lines.append(f"- Previous snapshot: `{prev_path.relative_to(ROOT)}`")
    lines.append(
        "- "
        f"Replay requests processed: {operations.get('replay_count', 0)} (last: {operations.get('last_replay_timestamp') or 'n/a'})."
    )
    lines.append(
        "- "
        f"Remediation backlog: {operations.get('remediation_backlog', 0)} open tasks across {operations.get('remediation_total', 0)} recorded actions."
    )
    return "\n".join(lines)


def _update_system_status(system_status_path: Path, block: str) -> None:
    if not system_status_path.exists():
        raise FileNotFoundError(f"system status file not found: {system_status_path}")
    text = system_status_path.read_text(encoding="utf-8")
    start_marker = text.find(DASHBOARD_BLOCK_START)
    end_marker = text.find(DASHBOARD_BLOCK_END, start_marker)
    if start_marker == -1 or end_marker == -1:
        raise ValueError("dashboard markers not found in SYSTEM_STATUS.md")
    block_start = text.rfind("\n", 0, start_marker)
    block_start = block_start + 1 if block_start != -1 else 0
    block_end = text.find("\n", end_marker)
    block_end = block_end + 1 if block_end != -1 else len(text)
    replacement = (
        f"{DASHBOARD_BLOCK_START}\n{block.strip()}\n{DASHBOARD_BLOCK_END}\n"
    )
    updated = text[:block_start] + replacement + text[block_end:]
    system_status_path.write_text(updated, encoding="utf-8")


def _generate_system_summary_block(dashboard: Dict[str, Any], operations: Optional[Dict[str, Any]] = None) -> str:
    latest = dashboard.get("latest_run", {})
    aggregate = latest.get("aggregate_metrics", {})
    snapshot = dashboard.get("coverage_snapshot", {})
    diff_summary = latest.get("diff_summary", {})
    operations = operations or {}

    playlist_id = latest.get("playlist_id", "n/a")
    run_id = latest.get("run_id", "n/a")
    latency_span = snapshot.get("tinyllama_latency_span_ms", "n/a")

    lines: List[str] = ["### Dashboard Highlights", ""]
    lines.append(
        "- "
        f"Playlist `{playlist_id}` run `{run_id}` captured {aggregate.get('scenario_count', 0)} scenarios "
        f"with {aggregate.get('failures', 0)} failures and latency span {latency_span} ms."
    )
    lines.append(
        "- "
        f"Coverage snapshot lists {len(snapshot.get('failing_scenarios', []))} failing scenarios and "
        f"{len(snapshot.get('pytest_targets', []))} pytest targets."
    )
    lines.append(
        "- "
        f"Diff baseline `{diff_summary.get('baseline_artifact') or 'none'}` with aggregate delta "
        f"{diff_summary.get('aggregate_delta', {}) or '{}'}; archival artifact `{latest.get('artifact_path', 'n/a')}`."
    )

    status_map: Dict[str, List[str]] = {}
    for highlight in dashboard.get("scenario_highlights", []):
        coverage = highlight.get("coverage", {})
        coverage_status = coverage.get("status", "unknown")
        status_map.setdefault(coverage_status, []).append(highlight.get("scenario_id", "unknown"))
    if status_map:
        pieces = []
        for status, scenarios in sorted(status_map.items()):
            pieces.append(f"{status}: {', '.join(sorted(filter(None, scenarios)))}")
        lines.append("- Scenario coverage distribution -> " + "; ".join(pieces))

    regressions = diff_summary.get("scenario_regressions", [])
    if regressions:
        lines.append("- Regressions detected: " + ", ".join(
            f"{item.get('scenario_id')} (latency_delta_ms={item.get('latency_delta_ms')})"
            for item in regressions
        ))
    else:
        lines.append("- No scenario regressions detected against the previous baseline.")

    prev_path = _include_previous_snapshot()
    if prev_path:
        lines.append(f"- Previous snapshot reference `{prev_path.relative_to(ROOT)}`")
    lines.append(
        "- "
        f"Replay cadence => {operations.get('replay_count', 0)} runs (last `{operations.get('last_replay_timestamp') or 'n/a'}`); remediation backlog {operations.get('remediation_backlog', 0)}."
    )
    return "\n".join(lines)


def _update_system_summary(summary_path: Path, block: str) -> None:
    if not summary_path.exists():
        raise FileNotFoundError(f"system summary file not found: {summary_path}")
    text = summary_path.read_text(encoding="utf-8")
    start_marker = text.find(SUMMARY_BLOCK_START)
    end_marker = text.find(SUMMARY_BLOCK_END, start_marker)
    if start_marker == -1 or end_marker == -1:
        raise ValueError("dashboard summary markers not found in SYSTEM_SUMMARY.md")
    block_start = text.rfind("\n", 0, start_marker)
    block_start = block_start + 1 if block_start != -1 else 0
    block_end = text.find("\n", end_marker)
    block_end = block_end + 1 if block_end != -1 else len(text)
    replacement = f"{SUMMARY_BLOCK_START}\n{block.strip()}\n{SUMMARY_BLOCK_END}\n"
    updated = text[:block_start] + replacement + text[block_end:]
    summary_path.write_text(updated, encoding="utf-8")


def main(argv: List[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Render benchmarking dashboard summaries",
    )
    parser.add_argument(
        "--dashboard-path",
        type=Path,
        default=DEFAULT_DASHBOARD_PATH,
        help="Path to ai_docs/benchmarking_dashboard.json",
    )
    parser.add_argument(
        "--update-system-status",
        action="store_true",
        help="Rewrite the SYSTEM_STATUS.md dashboard section",
    )
    parser.add_argument(
        "--system-status-path",
        type=Path,
        default=SYSTEM_STATUS_PATH,
        help="Path to SYSTEM_STATUS.md when using --update-system-status",
    )
    parser.add_argument(
        "--update-system-summary",
        action="store_true",
        help="Rewrite the SYSTEM_SUMMARY.md dashboard section",
    )
    parser.add_argument(
        "--system-summary-path",
        type=Path,
        default=SYSTEM_SUMMARY_PATH,
        help="Path to SYSTEM_SUMMARY.md when using --update-system-summary",
    )
    args = parser.parse_args(argv)
    dashboard = _load_dashboard(args.dashboard_path)
    operations = benchmark_operations.load_summary()
    print(render_dashboard(dashboard))
    if args.update_system_status:
        block = _generate_system_status_block(dashboard, operations)
        _update_system_status(args.system_status_path, block)
    if args.update_system_summary:
        summary_block = _generate_system_summary_block(dashboard, operations)
        _update_system_summary(args.system_summary_path, summary_block)
if __name__ == "__main__":  # pragma: no cover - manual invocation hook
    main()
