"""Generate governance markdown snippets from benchmarking dashboard data."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_PATH = ROOT / "ai_docs" / "benchmarking_dashboard.json"
SYSTEM_STATUS_PATH = ROOT / "SYSTEM_STATUS.md"
SYSTEM_SUMMARY_PATH = ROOT / "SYSTEM_SUMMARY.md"

SNIPPET_START = "<!-- dashboard:begin -->"
SNIPPET_END = "<!-- dashboard:end -->"


def _load_dashboard() -> Dict[str, Any]:
    if not DASHBOARD_PATH.exists():
        raise FileNotFoundError("benchmarking_dashboard.json missing")
    return json.loads(DASHBOARD_PATH.read_text(encoding="utf-8"))


def _render_snippet(dashboard: Dict[str, Any]) -> str:
    latest = dashboard.get("latest_run", {})
    aggregate = latest.get("aggregate_metrics", {})
    coverage_snapshot = dashboard.get("coverage_snapshot", {})
    lines = ["### Benchmarking Dashboard Snapshot", ""]
    lines.append(
        f"- Playlist `{latest.get('playlist_id', 'n/a')}` run `{latest.get('run_id', 'n/a')}` captured {aggregate.get('scenario_count', 0)} scenarios with {aggregate.get('failures', 0)} failures and TinyLLaMA latency range {aggregate.get('tinyllama_latency_min_ms', 'n/a')}–{aggregate.get('tinyllama_latency_max_ms', 'n/a')} ms."
    )
    lines.append(
        f"- Coverage Snapshot: {coverage_snapshot.get('scenario_count', 0)} scenarios, {len(coverage_snapshot.get('failing_scenarios', []))} failing, latency span {coverage_snapshot.get('tinyllama_latency_span_ms', 'n/a')} ms, pytest targets {len(coverage_snapshot.get('pytest_targets', []))}."
    )
    lines.append("- Scenario Coverage Highlights:")
    for highlight in dashboard.get("scenario_highlights", []):
        coverage = highlight.get("coverage", {})
        presentation = highlight.get("presentation", {})
        severity = presentation.get("max_alert_severity") or presentation.get("pressure_state", {}).get("severity")
        missing = [k for k, v in coverage.get("requirements", {}).items() if not v]
        lines.append(
            f"  - `{highlight.get('scenario_id')}` coverage **{coverage.get('status')}** (missing: {', '.join(missing) or 'none'}), severity `{severity or 'none'}`."
        )
    return "\n".join(lines)


def _replace_snippet(path: Path, snippet: str) -> None:
    if not path.exists():
        raise FileNotFoundError(path)
    text = path.read_text(encoding="utf-8")
    if SNIPPET_START in text and SNIPPET_END in text:
        start = text.index(SNIPPET_START)
        end = text.index(SNIPPET_END) + len(SNIPPET_END)
        new_text = text[:start] + SNIPPET_START + "\n" + snippet + "\n" + SNIPPET_END + text[end:]
    else:
        new_text = text + "\n\n" + SNIPPET_START + "\n" + snippet + "\n" + SNIPPET_END + "\n"
    path.write_text(new_text, encoding="utf-8")


def sync_dashboard_docs() -> None:
    dashboard = _load_dashboard()
    snippet = _render_snippet(dashboard)
    _replace_snippet(SYSTEM_STATUS_PATH, snippet)
    _replace_snippet(SYSTEM_SUMMARY_PATH, snippet)


+if __name__ == "__main__":
+    sync_dashboard_docs()
