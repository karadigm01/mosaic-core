"""Automation runner utilities for recording governance validation runs."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
AUTOMATION_RUNS_PATH = ROOT / "knowledge_base" / "automation_runs" / "index.json"
KB_INDEX_PATH = ROOT / "knowledge_base" / "kb_index.json"
LOG_DIR = ROOT / "logs"
DEFAULT_COMPONENT_INDEX = ROOT / "ai_docs" / "component_index.json"

from runtime.component_coverage_sync import update_component_index_from_coverage
from runtime.tinyllama_health import TinyLlamaHealthMonitor, TinyLlamaHealthSnapshot
from runtime import benchmarking_runner


@dataclass
class AutomationRun:
    """Structured automation run payload persisted to the knowledge base."""

    run_id: str
    pattern_id: str
    automation_type: str
    start_timestamp: str
    end_timestamp: str
    status: str
    executor: str
    evidence: Dict[str, object]
    notes: str


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sanitize_tag(ts: str) -> str:
    return ts.replace(":", "").replace("-", "").replace("Z", "")


def _extract_metric(label: str, output: str) -> int:
    match = re.search(rf"(\d+) {label}", output)
    return int(match.group(1)) if match else 0


def _relative_to_root(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _load_index(index_path: Path) -> Dict[str, object]:
    if not index_path.exists():
        raise FileNotFoundError(f"Automation index missing: {index_path}")
    return json.loads(index_path.read_text(encoding="utf-8"))


def _write_index(index_path: Path, data: Dict[str, object]) -> None:
    data["last_updated"] = _utc_timestamp()
    index_path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _append_run(run: AutomationRun, index_path: Path) -> None:
    data = _load_index(index_path)
    runs: List[Dict[str, object]] = data.setdefault("runs", [])
    runs.append(asdict(run))
    _write_index(index_path, data)


def _record_latest_health_snapshot(snapshot: TinyLlamaHealthSnapshot) -> None:
    if not KB_INDEX_PATH.exists():
        return
    data = json.loads(KB_INDEX_PATH.read_text(encoding="utf-8"))
    data["latest_tinyllama_health_snapshot"] = snapshot.to_dict()
    data["last_updated"] = _utc_timestamp()
    KB_INDEX_PATH.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _capture_cli_demo(run_tag: str, health_snapshot: TinyLlamaHealthSnapshot) -> Dict[str, object]:
    if not health_snapshot.is_available:
        return {
            "status": "skipped",
            "reason": health_snapshot.failure_reason or "tinyllama_unavailable",
            "artifact": None,
        }
    demo_path = LOG_DIR / f"hallucinator-demo-{run_tag}.json"
    try:
        result = subprocess.run(  # noqa: S603
            [sys.executable, "-m", "main", "--demo", "imagination"],
            capture_output=True,
            text=True,
            cwd=ROOT,
            timeout=45,
        )
        demo_path.write_text(result.stdout, encoding="utf-8")
        metadata: Dict[str, object] = {
            "status": "success" if result.returncode == 0 else "failed",
            "artifact": _relative_to_root(demo_path),
            "return_code": result.returncode,
        }
        if result.returncode != 0:
            metadata["stderr"] = result.stderr.strip()
        else:
            try:
                metadata["result_summary"] = json.loads(result.stdout).get("result_summary")
            except json.JSONDecodeError:
                metadata["result_summary"] = None
        return metadata
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "error",
            "reason": repr(exc),
            "artifact": None,
        }


def run_multi_hop_validation(
    pytest_args: Optional[List[str]] = None,
    pattern_id: str = "auto-0003",
    ledger_reference: Optional[str] = None,
    notes: str = "Automated multi-hop validation run",
    enable_coverage_sync: bool = False,
    component_index_path: Optional[Path] = None,
    automation_runs_path: Optional[Path] = None,
    benchmark_playlist: Optional[str] = None,
) -> Tuple[AutomationRun, Optional[AutomationRun]]:
    """Execute pytest, record the automation run, and optionally sync coverage."""

    automation_index = (automation_runs_path or AUTOMATION_RUNS_PATH).resolve()
    start_ts = _utc_timestamp()
    sanitized_tag = _sanitize_tag(start_ts)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"tests-{sanitized_tag}.log"

    monitor = TinyLlamaHealthMonitor()
    health_snapshot = monitor.ensure_fresh(timeout=1.5)

    command: List[str]
    if enable_coverage_sync:
        command = [sys.executable, "-m", "coverage", "run", "-m", "pytest"] + (pytest_args or ["tests"])
    else:
        command = ["pytest"] + (pytest_args or ["tests"])
    result = subprocess.run(command, capture_output=True, text=True, cwd=ROOT)
    combined_output = result.stdout + "\n" + result.stderr
    log_path.write_text(combined_output, encoding="utf-8")

    end_ts = _utc_timestamp()
    passed = _extract_metric("passed", combined_output)
    failed = _extract_metric("failed", combined_output)
    tests_executed = passed + failed
    status = "success" if result.returncode == 0 else "failed"
    cli_demo_metadata = _capture_cli_demo(sanitized_tag, health_snapshot)
    evidence = {
        "command": " ".join(command),
        "tests_executed": tests_executed,
        "tests_passed": passed,
        "tests_failed": failed,
        "evidence_artifact": str(log_path.relative_to(ROOT)),
        "ledger_reference": ledger_reference or f"proof://automation/{pattern_id}-{sanitized_tag}",
        "tinyllama_health_snapshot": health_snapshot.to_dict(),
        "hallucinator_cli_demo": cli_demo_metadata,
    }

    if benchmark_playlist:
        playlist_result = benchmarking_runner.run_playlist(benchmark_playlist)
        evidence["benchmark_playlist"] = {
            "playlist_id": playlist_result["playlist_id"],
            "artifact_path": playlist_result.get("artifact_path"),
            "run_id": playlist_result.get("run_id"),
            "aggregate_metrics": playlist_result.get("aggregate_metrics"),
        }

    run = AutomationRun(
        run_id=f"{pattern_id}-run-{sanitized_tag}",
        pattern_id=pattern_id,
        automation_type="validation",
        start_timestamp=start_ts,
        end_timestamp=end_ts,
        status=status,
        executor="pytest",
        evidence=evidence,
        notes=notes,
    )
    _append_run(run, automation_index)
    _record_latest_health_snapshot(health_snapshot)

    coverage_run: Optional[AutomationRun] = None
    if enable_coverage_sync:
        coverage_run = _handle_coverage_sync(
            sanitized_tag,
            status,
            component_index_path or DEFAULT_COMPONENT_INDEX,
            automation_index,
        )

    return run, coverage_run


def _handle_coverage_sync(run_tag: str, test_status: str, component_index_path: Path, automation_index_path: Path) -> AutomationRun:
    component_index = component_index_path.resolve()
    start_ts = _utc_timestamp()

    if test_status != "success":
        run = AutomationRun(
            run_id=f"auto-0006-run-{run_tag}",
            pattern_id="auto-0006",
            automation_type="documentation",
            start_timestamp=start_ts,
            end_timestamp=_utc_timestamp(),
            status="skipped",
            executor="coverage",
            evidence={"reason": "pytest_failed"},
            notes="Coverage sync skipped because pytest failed",
        )
        _append_run(run, automation_index_path)
        return run

    coverage_json = LOG_DIR / f"coverage-{run_tag}.json"
    evidence: Dict[str, object] = {
        "coverage_report": _relative_to_root(coverage_json),
        "component_index": _relative_to_root(component_index),
    }
    coverage_status = "success"
    updates_count = 0
    notes = "Coverage sync completed"

    try:
        subprocess.run(
            [sys.executable, "-m", "coverage", "json", "-o", str(coverage_json)],
            check=True,
            cwd=ROOT,
        )
        updates = update_component_index_from_coverage(coverage_json, component_index, ROOT)
        updates_count = len(updates)
        evidence["updated_components"] = [update.component_id for update in updates]
        evidence["updated_files"] = [update.file_path for update in updates]
        notes = f"Updated {updates_count} component entries via coverage sync"
    except subprocess.CalledProcessError as exc:
        coverage_status = "failed"
        notes = f"Coverage tool error: {exc}"
        evidence["error"] = str(exc)
    except Exception as exc:  # noqa: BLE001
        coverage_status = "failed"
        notes = f"Coverage sync error: {exc}"
        evidence["error"] = repr(exc)
    finally:
        subprocess.run([sys.executable, "-m", "coverage", "erase"], cwd=ROOT, check=False)

    run = AutomationRun(
        run_id=f"auto-0006-run-{run_tag}",
        pattern_id="auto-0006",
        automation_type="documentation",
        start_timestamp=start_ts,
        end_timestamp=_utc_timestamp(),
        status="success" if coverage_status == "success" else coverage_status,
        executor="coverage",
        evidence=evidence,
        notes=notes,
    )
    _append_run(run, automation_index_path)
    return run


def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Automation runner for multi-hop validation")
    parser.add_argument(
        "--pattern-id",
        default="auto-0003",
        help="Automation pattern identifier to record",
    )
    parser.add_argument(
        "--ledger-ref",
        default=None,
        help="Optional ledger reference override",
    )
    parser.add_argument(
        "--notes",
        default="Automated multi-hop validation run",
        help="Notes to attach to the automation entry",
    )
    parser.add_argument(
        "--enable-coverage-sync",
        action="store_true",
        help="Run coverage instrumentation and sync component_index metadata",
    )
    parser.add_argument(
        "--component-index",
        default=str(DEFAULT_COMPONENT_INDEX),
        help="Component index path to update when coverage sync is enabled",
    )
    parser.add_argument(
        "--automation-index",
        default=None,
        help="Automation runs index path to record run metadata (defaults to knowledge_base/automation_runs/index.json)",
    )
    parser.add_argument(
        "--benchmark-playlist",
        default=None,
        help="Optional benchmarking playlist identifier to execute after pytest (delegates to benchmarking_runner)",
    )
    parser.add_argument(
        "pytest_args",
        nargs=argparse.REMAINDER,
        help="Arguments passed directly to pytest (defaults to 'tests')",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> None:
    args = _parse_args(argv)
    pytest_args = args.pytest_args if args.pytest_args else ["tests"]
    component_index = Path(args.component_index)
    if not component_index.is_absolute():
        component_index = (ROOT / component_index).resolve()
    automation_index = Path(args.automation_index).resolve() if args.automation_index else None
    run, coverage_run = run_multi_hop_validation(
        pytest_args=pytest_args,
        pattern_id=args.pattern_id,
        ledger_reference=args.ledger_ref,
        notes=args.notes,
        enable_coverage_sync=args.enable_coverage_sync,
        component_index_path=component_index,
        automation_runs_path=automation_index,
        benchmark_playlist=args.benchmark_playlist,
    )
    print(json.dumps(asdict(run), indent=2))
    if coverage_run:
        print(json.dumps(asdict(coverage_run), indent=2))


if __name__ == "__main__":
    main()
