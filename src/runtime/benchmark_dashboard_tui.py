"""Terminal dashboard for benchmark governance controls."""
from __future__ import annotations

import argparse
import curses
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from urllib import error as urlerror
from urllib import request as urlrequest
from urllib.parse import urlencode

from runtime import benchmark_operations, benchmarking_runner
from runtime.benchmark_dashboard_service import (
    BenchmarkDashboardDataSource,
    DEFAULT_DASHBOARD_PATH,
    DEFAULT_HISTORY_DIR,
    DEFAULT_KB_INDEX_PATH,
)

ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_DIR = Path("logs/benchmarks")


def _resolve_repo_path(path_str: str) -> Optional[Path]:
    candidate = Path(path_str)
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    try:
        resolved = candidate.resolve()
    except OSError:
        return None
    try:
        resolved.relative_to(ROOT)
    except ValueError:
        return None
    return resolved


class DashboardController:
    """Protocol for dashboard data providers."""

    def load_state(self) -> Dict[str, Any]:  # pragma: no cover - interface only
        raise NotImplementedError

    def replay_scenario(self, scenario_id: str) -> None:  # pragma: no cover - interface only
        raise NotImplementedError

    def log_remediation_task(self, scenario_id: str, reason: Optional[str] = None) -> None:  # pragma: no cover
        raise NotImplementedError

    def run_remediation_pytest(self, scenario_id: str) -> None:  # pragma: no cover
        raise NotImplementedError

    def read_artifact_text(self, path: str) -> Optional[str]:  # pragma: no cover - interface only
        raise NotImplementedError


class LocalDashboardController(DashboardController):
    """Loads dashboard state and runs replay/remediation actions locally."""

    def __init__(
        self,
        dashboard_path: Path,
        history_dir: Path,
        kb_index_path: Path,
    ) -> None:
        self.data_source = BenchmarkDashboardDataSource(
            dashboard_path=dashboard_path,
            history_dir=history_dir,
            kb_index_path=kb_index_path,
        )

    def load_state(self) -> Dict[str, Any]:
        state = self.data_source.build_state(history_limit=5, include_history_payload=True)
        state["operations"] = benchmark_operations.load_summary()
        return state

    def replay_scenario(self, scenario_id: str) -> None:
        evidence = benchmarking_runner.run_scenario(scenario_id)
        benchmark_operations.record_replay_event(
            scenario_id,
            evidence.get("run_id"),
            evidence.get("artifact_path"),
            (evidence.get("command_result") or {}).get("return_code"),
        )

    def log_remediation_task(self, scenario_id: str, reason: Optional[str] = None) -> None:
        benchmark_operations.record_remediation_event(
            scenario_id,
            action="open_task",
            status="open",
            details={"reason": reason} if reason else None,
        )

    def run_remediation_pytest(self, scenario_id: str) -> None:
        evidence = benchmarking_runner.run_scenario(scenario_id)
        return_code = (evidence.get("command_result") or {}).get("return_code")
        status = "closed" if return_code == 0 else "needs_follow_up"
        benchmark_operations.record_remediation_event(
            scenario_id,
            action="pytest_subset",
            status=status,
            details={
                "run_id": evidence.get("run_id"),
                "artifact_path": evidence.get("artifact_path"),
                "return_code": return_code,
            },
        )

    def read_artifact_text(self, path: str) -> Optional[str]:
        resolved = _resolve_repo_path(path)
        if not resolved or not resolved.is_file():
            return None
        try:
            return resolved.read_text(encoding="utf-8")
        except OSError:
            return None


class RemoteDashboardController(DashboardController):
    """Uses the dashboard HTTP service for data and actions."""

    def __init__(self, endpoint: str) -> None:
        self.endpoint = endpoint.rstrip("/")

    def load_state(self) -> Dict[str, Any]:
        url = f"{self.endpoint}/api/dashboard?history_limit=5&include_payload=1"
        try:
            with urlrequest.urlopen(url, timeout=10) as response:
                payload = response.read().decode("utf-8")
        except urlerror.URLError as exc:
            raise RuntimeError(f"API request failed: {exc}") from exc
        return json.loads(payload)

    def replay_scenario(self, scenario_id: str) -> None:
        self._post_json("/api/replay", {"scenario_id": scenario_id})

    def log_remediation_task(self, scenario_id: str, reason: Optional[str] = None) -> None:
        body: Dict[str, Any] = {"scenario_id": scenario_id, "action": "open_task"}
        if reason:
            body["reason"] = reason
        self._post_json("/api/remediation", body)

    def run_remediation_pytest(self, scenario_id: str) -> None:
        self._post_json(
            "/api/remediation",
            {"scenario_id": scenario_id, "action": "pytest_subset"},
        )

    def read_artifact_text(self, path: str) -> Optional[str]:
        try:
            payload = self._post_json("/api/artifact", {"path": path})
        except RuntimeError:
            return None
        return payload.get("content")

    def _post_json(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.endpoint}{path}"
        data = json.dumps(payload).encode("utf-8")
        request = urlrequest.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlrequest.urlopen(request, timeout=15) as response:
                body = response.read().decode("utf-8")
        except urlerror.HTTPError as exc:
            raise RuntimeError(f"API {path} failed: {exc.status} {exc.reason}") from exc
        except urlerror.URLError as exc:
            raise RuntimeError(f"API request failed: {exc.reason}") from exc
        return json.loads(body)


class BenchmarkDashboardTUI:
    """Lightweight curses UI for dashboard telemetry and controls."""

    def __init__(self, controller: DashboardController) -> None:
        self.controller = controller
        self.state: Dict[str, Any] = {}
        self.selected_index = 0
        self.status_message: Optional[str] = None
        self.error_message: Optional[str] = None
        self.status_filter: Optional[str] = None
        self.history_filter_index: Optional[int] = None

    def run(self) -> None:
        curses.wrapper(self._main)

    def _main(self, screen: "curses._CursesWindow") -> None:  # type: ignore[name-defined]
        curses.curs_set(0)
        screen.nodelay(False)
        self._refresh_state()
        while True:
            self._draw(screen)
            key = screen.getch()
            if key in (ord("q"), ord("Q")):
                break
            if key in (ord("r"), ord("R")):
                self._trigger_action(screen, "Replay", self._replay_selected)
            elif key in (ord("o"), ord("O")):
                self._trigger_action(screen, "Remediation task", self._open_task_selected)
            elif key in (ord("p"), ord("P")):
                self._trigger_action(screen, "Pytest subset", self._pytest_selected)
            elif key in (ord("j"), curses.KEY_DOWN):
                self._move_selection(1)
            elif key in (ord("k"), curses.KEY_UP):
                self._move_selection(-1)
            elif key == ord("g"):
                self.selected_index = 0
            elif key == ord("G"):
                self.selected_index = max(0, len(self._scenario_highlights()) - 1)
            elif key in (ord("f"), ord("F")):
                self._refresh_state()
            elif key in (ord("s"), ord("S")):
                self._cycle_status_filter()
            elif key == ord("]"):
                self._cycle_history_filter(1)
            elif key == ord("["):
                self._cycle_history_filter(-1)
            elif key in (ord("c"), ord("C")):
                self.history_filter_index = None
            elif key in (ord("d"), 10, 13):
                self._open_selected_artifact(screen)
            elif key == ord("D"):
                self._open_history_snapshot(screen)

    def _move_selection(self, delta: int) -> None:
        scenarios = self._scenario_highlights()
        if not scenarios:
            self.selected_index = 0
            return
        self.selected_index = max(0, min(self.selected_index + delta, len(scenarios) - 1))

    def _scenario_highlights(self) -> List[Dict[str, Any]]:
        payload = self._active_payload()
        highlights = list(payload.get("scenario_highlights", []) or [])
        if self.status_filter:
            highlights = [
                h
                for h in highlights
                if (h.get("coverage", {}).get("status") or "unknown") == self.status_filter
            ]
        return highlights

    def _refresh_state(self) -> None:
        try:
            self.state = self.controller.load_state()
            self.status_message = "Refreshed"
            self.error_message = None
            history_entries = self._history_entries()
            if not history_entries:
                self.history_filter_index = None
            elif self.history_filter_index is not None and self.history_filter_index >= len(history_entries):
                self.history_filter_index = len(history_entries) - 1
        except Exception as exc:  # pragma: no cover - defensive
            self.error_message = f"Refresh failed: {exc}"

    def _history_entries(self) -> List[Dict[str, Any]]:
        return list(self.state.get("history", []) or [])

    def _active_payload(self) -> Dict[str, Any]:
        if self.history_filter_index is None:
            return self.state.get("dashboard", {})
        entries = self._history_entries()
        if not entries:
            self.history_filter_index = None
            return self.state.get("dashboard", {})
        idx = max(0, min(self.history_filter_index, len(entries) - 1))
        entry = entries[idx]
        payload = entry.get("payload")
        if payload:
            return payload
        path = entry.get("path")
        if path:
            content = self.controller.read_artifact_text(str(path))
            if content is not None:
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    pass
        return self.state.get("dashboard", {})

    def _available_statuses(self) -> List[str]:
        statuses = {
            (highlight.get("coverage", {}).get("status") or "unknown")
            for highlight in self._active_payload().get("scenario_highlights", []) or []
        }
        statuses.discard("unknown")
        return sorted(statuses)

    def _cycle_status_filter(self) -> None:
        statuses = self._available_statuses()
        if not statuses:
            self.status_filter = None
            return
        order = statuses + [None]
        current = order.index(self.status_filter) if self.status_filter in order else len(order) - 1
        next_index = (current + 1) % len(order)
        self.status_filter = order[next_index]
        self.selected_index = 0

    def _cycle_history_filter(self, delta: int) -> None:
        entries = self._history_entries()
        total = len(entries)
        if total == 0:
            self.history_filter_index = None
            return
        current = self.history_filter_index if self.history_filter_index is not None else total
        current = (current + delta) % (total + 1)
        self.history_filter_index = None if current == total else current
        self.selected_index = 0

    @staticmethod
    def _resolve_path(path_str: str) -> Path:
        candidate = Path(path_str)
        if not candidate.is_absolute():
            candidate = ROOT / candidate
        return candidate

    def _draw(self, screen: "curses._CursesWindow") -> None:  # type: ignore[name-defined]
        screen.erase()
        max_y, max_x = screen.getmaxyx()
        row = 0
        for line in self._summary_lines(max_x):
            if row >= max_y:
                break
            screen.addnstr(row, 0, line, max_x - 1)
            row += 1
        row += 1
        if row < max_y:
            screen.addnstr(row, 0, "Scenario Highlights", max_x - 1, curses.A_BOLD)
            row += 1
        scenarios = self._scenario_highlights()
        for idx, highlight in enumerate(scenarios):
            if row >= max_y:
                break
            prefix = "> " if idx == self.selected_index else "  "
            line = f"{prefix}{highlight.get('scenario_id')} | {highlight.get('coverage', {}).get('status', 'unknown')} | latency {highlight.get('tinyllama_latency_ms', 'n/a')} ms | return {highlight.get('return_code', 'n/a')}"
            attr = curses.A_REVERSE if idx == self.selected_index else curses.A_NORMAL
            screen.addnstr(row, 0, line[: max_x - 1], max_x - 1, attr)
            row += 1
        row += 1
        for line in self._operations_lines():
            if row >= max_y:
                break
            screen.addnstr(row, 0, line, max_x - 1)
            row += 1
        row += 1
        for line in self._history_lines():
            if row >= max_y:
                break
            screen.addnstr(row, 0, line, max_x - 1)
            row += 1
        row = max_y - 3
        if row >= 0:
            status = self.error_message or self.status_message or ""
            screen.addnstr(row, 0, status[: max_x - 1], max_x - 1, curses.A_BOLD if self.error_message else curses.A_DIM)
        instructions = (
            "Keys: j/k move | r replay | o task | p pytest | s status | [/ ] snapshot | c clear | d open | D history | f refresh | q quit"
        )
        screen.addnstr(max_y - 1, 0, instructions[: max_x - 1], max_x - 1, curses.A_DIM)
        screen.refresh()

    def _summary_lines(self, width: int) -> List[str]:
        dashboard = self._active_payload()
        latest = dashboard.get("latest_run", {})
        coverage = dashboard.get("coverage_snapshot", {})
        health = self.state.get("tinyllama_health", {})
        snapshot_label = self._snapshot_label()
        lines = [
            f"Playlist {latest.get('playlist_id', 'n/a')} | Run {latest.get('run_id', 'n/a')} | Latency span {coverage.get('tinyllama_latency_span_ms', 'n/a')} ms",
            f"Scenarios {coverage.get('scenario_count', len(self._scenario_highlights()))} | Pytest targets {len(coverage.get('pytest_targets', []) or [])} | Failures {len(coverage.get('failing_scenarios', []) or [])}",
            f"TinyLLaMA status {health.get('status_code', 'n/a')} | latency {health.get('latency_ms', 'n/a')} ms | failure {health.get('failure_reason') or 'none'}",
            f"Snapshot {snapshot_label} | Status filter {self.status_filter or 'all'}",
        ]
        return [line[: width - 1] for line in lines]

    def _operations_lines(self) -> List[str]:
        operations = self.state.get("operations", {})
        lines = [
            "Operations:",
            f"  Replays: {operations.get('replay_count', 0)} (last {operations.get('last_replay_timestamp') or 'n/a'})",
            f"  Remediation backlog: {operations.get('remediation_backlog', 0)} / total {operations.get('remediation_total', 0)}",
        ]
        recent_replays = operations.get("recent_replays") or []
        if recent_replays:
            lines.append("  Recent replays:")
            for entry in recent_replays[-3:]:
                lines.append(f"    - {entry.get('scenario_id')} run {entry.get('run_id')} return {entry.get('return_code')}")
        recent_remediations = operations.get("recent_remediations") or []
        if recent_remediations:
            lines.append("  Recent remediations:")
            for entry in recent_remediations[-3:]:
                lines.append(
                    f"    - {entry.get('scenario_id')} {entry.get('action')} {entry.get('status')}"
                )
        return lines

    def _history_lines(self) -> List[str]:
        history = self._history_entries()
        lines = ["History snapshots (cycle with [ / ]):"]
        for idx, entry in enumerate(history[:5]):
            marker = "*" if self.history_filter_index == idx else "-"
            lines.append(
                f"  {marker} {entry.get('playlist_id', 'n/a')} run {entry.get('run_id', 'n/a')} ({entry.get('path')})"
            )
        return lines

    def _snapshot_label(self) -> str:
        if self.history_filter_index is None:
            latest = self.state.get("dashboard", {}).get("latest_run", {})
            return f"current ({latest.get('playlist_id', 'n/a')})"
        entries = self._history_entries()
        if not entries:
            return "current"
        entry = entries[self.history_filter_index]
        return f"history {entry.get('playlist_id', 'n/a')}"

    def _artifact_path_for_selected_scenario(self) -> Optional[Path]:
        scenario_id = self._selected_scenario_id()
        if not scenario_id:
            return None
        operations = self.state.get("operations", {})
        for entry in reversed(operations.get("recent_replays", []) or []):
            if entry.get("scenario_id") == scenario_id and entry.get("artifact_path"):
                return self._resolve_path(entry["artifact_path"])
        payload = self._active_payload()
        for highlight in payload.get("scenario_highlights", []) or []:
            if highlight.get("scenario_id") == scenario_id:
                run_id = highlight.get("run_id")
                if run_id:
                    candidate = ARTIFACT_DIR / f"{run_id}.json"
                    if candidate.exists():
                        return candidate
        return None

    def _open_selected_artifact(self, screen: "curses._CursesWindow") -> None:  # type: ignore[name-defined]
        path = self._artifact_path_for_selected_scenario()
        if not path:
            self.error_message = "No artifact for scenario"
            return
        content = self.controller.read_artifact_text(str(path))
        if content is None:
            self.error_message = "Artifact unavailable"
            return
        self._display_artifact(screen, path, content)
        self.status_message = f"Opened {path}"

    def _open_history_snapshot(self, screen: "curses._CursesWindow") -> None:  # type: ignore[name-defined]
        if self.history_filter_index is None:
            self.error_message = "Select a history snapshot first"
            return
        entries = self._history_entries()
        if not entries or self.history_filter_index >= len(entries):
            self.error_message = "No snapshot available"
            return
        path = entries[self.history_filter_index].get("path")
        if not path:
            self.error_message = "Snapshot path unknown"
            return
        content = self.controller.read_artifact_text(str(path))
        if content is None:
            self.error_message = "Snapshot unavailable"
            return
        resolved = self._resolve_path(path)
        self._display_artifact(screen, resolved, content)
        self.status_message = f"Opened {resolved}"

    def _display_artifact(self, screen: "curses._CursesWindow", path: Path, content: str) -> None:  # type: ignore[name-defined]
        if path.exists():
            self._launch_pager(screen, path)
            return
        self._launch_pager_with_text(screen, content, path.name or "artifact.json")

    def _launch_pager(self, screen: "curses._CursesWindow", path: Path) -> None:  # type: ignore[name-defined]
        curses.def_prog_mode()
        curses.endwin()
        pager_cmd = os.environ.get("PAGER", "less")
        args = pager_cmd.split()
        if not args:
            args = ["less"]
        args.append(str(path))
        try:
            subprocess.run(args, check=False)
        finally:
            curses.reset_prog_mode()
            screen.refresh()

    def _launch_pager_with_text(
        self,
        screen: "curses._CursesWindow",  # type: ignore[name-defined]
        content: str,
        label: str,
    ) -> None:
        suffix = Path(label).suffix or ".json"
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile("w", delete=False, suffix=suffix) as handle:
                handle.write(content)
                temp_path = Path(handle.name)
        except OSError:
            self.error_message = "Failed to render artifact"
            return
        try:
            self._launch_pager(screen, temp_path)
        finally:
            if temp_path:
                try:
                    temp_path.unlink()
                except OSError:
                    pass

    def _selected_scenario_id(self) -> Optional[str]:
        scenarios = self._scenario_highlights()
        if not scenarios:
            return None
        index = max(0, min(self.selected_index, len(scenarios) - 1))
        return scenarios[index].get("scenario_id")

    def _trigger_action(
        self,
        screen: "curses._CursesWindow",  # type: ignore[name-defined]
        label: str,
        action: Optional[Callable[[], None]],
    ) -> None:
        if action is None:
            self.error_message = "No scenario selected"
            return
        try:
            self.status_message = f"{label} running..."
            self.error_message = None
            self._draw(screen)
            action()
            self.status_message = f"{label} complete"
            self._refresh_state()
        except Exception as exc:  # pragma: no cover - depends on runtime state
            self.error_message = f"{label} failed: {exc}"

    def _replay_selected(self) -> None:
        scenario_id = self._selected_scenario_id()
        if not scenario_id:
            raise ValueError("No scenario")
        self.controller.replay_scenario(scenario_id)

    def _open_task_selected(self) -> None:
        scenario_id = self._selected_scenario_id()
        if not scenario_id:
            raise ValueError("No scenario")
        self.controller.log_remediation_task(scenario_id)

    def _pytest_selected(self) -> None:
        scenario_id = self._selected_scenario_id()
        if not scenario_id:
            raise ValueError("No scenario")
        self.controller.run_remediation_pytest(scenario_id)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Terminal interface for benchmark dashboard controls")
    parser.add_argument("--dashboard-path", type=Path, default=DEFAULT_DASHBOARD_PATH)
    parser.add_argument("--history-dir", type=Path, default=DEFAULT_HISTORY_DIR)
    parser.add_argument("--kb-index-path", type=Path, default=DEFAULT_KB_INDEX_PATH)
    parser.add_argument("--api-endpoint", type=str, default=None, help="Dashboard API base URL (enables remote mode)")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> None:
    args = parse_args(argv)
    if args.api_endpoint:
        controller: DashboardController = RemoteDashboardController(args.api_endpoint)
    else:
        controller = LocalDashboardController(args.dashboard_path, args.history_dir, args.kb_index_path)
    tui = BenchmarkDashboardTUI(controller)
    tui.run()


if __name__ == "__main__":  # pragma: no cover - manual entry point
    main()
