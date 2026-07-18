from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from runtime import benchmark_dashboard_cli, benchmarking_runner
from runtime.tinyllama_health import TinyLlamaHealthSnapshot


def test_benchmarking_runner_executes_catalog_scenario(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    scenario_path = tmp_path / "benchmarking_scenarios.json"
    scenario_path.write_text(
        json.dumps(
            {
                "scenarios": [
                    {
                        "id": "scenario.test",
                        "demo": {"entry_point": "main", "arguments": ["--demo", "sentiment"]},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(benchmarking_runner, "SCENARIO_PATH", scenario_path)
    monkeypatch.setattr(benchmarking_runner, "EVIDENCE_DIR", tmp_path)
    kb_index = tmp_path / "automation_runs.json"
    kb_index.write_text(
        json.dumps({"last_updated": "2026-01-01T00:00:00Z", "runs": [], "schema_version": "1.0.0"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(benchmarking_runner, "AUTOMATION_RUNS_INDEX", kb_index)

    class StubMonitor:
        def ensure_fresh(self, timeout: float = 1.5) -> TinyLlamaHealthSnapshot:  # noqa: ARG002
            return TinyLlamaHealthSnapshot(True, 200, 10, None, 0.0)

    monkeypatch.setattr(benchmarking_runner, "TinyLlamaHealthMonitor", lambda: StubMonitor())
    monkeypatch.setattr(
        benchmarking_runner.subprocess,
        "run",
        lambda *_, **__: SimpleNamespace(returncode=0, stdout="{}", stderr=""),
    )

    evidence = benchmarking_runner._run_scenario("scenario.test")
    assert evidence["scenario_id"] == "scenario.test"
    assert evidence["health_snapshot"]["is_available"] is True
    assert "artifact_path" in evidence
    artifact_path = Path(evidence["artifact_path"])
    if not artifact_path.is_absolute():
        artifact_path = (Path(benchmarking_runner.ROOT) / artifact_path).resolve()
    assert artifact_path.exists()
    automation_runs = json.loads(kb_index.read_text(encoding="utf-8"))
    assert automation_runs["runs"], "automation run should be recorded"
    entry = automation_runs["runs"][-1]
    assert entry["evidence"]["scenario_id"] == "scenario.test"
    assert Path(benchmarking_runner.ROOT, entry["evidence"]["artifact_path"]).exists()


def test_benchmarking_runner_missing_scenario(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    scenario_path = tmp_path / "benchmarking_scenarios.json"
    scenario_path.write_text(json.dumps({"scenarios": []}), encoding="utf-8")
    monkeypatch.setattr(benchmarking_runner, "SCENARIO_PATH", scenario_path)
    monkeypatch.setattr(benchmarking_runner, "AUTOMATION_RUNS_INDEX", tmp_path / "automation_runs.json")
    with pytest.raises(ValueError):
        benchmarking_runner._run_scenario("missing")


def test_benchmarking_runner_playlist_records_aggregate(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    scenario_path = tmp_path / "benchmarking_scenarios.json"
    playlist_path = tmp_path / "benchmarking_playlists.json"
    evidence_dir = tmp_path / "benchmarks"
    automation_runs_path = tmp_path / "automation_runs.json"
    dashboard_path = tmp_path / "benchmarking_dashboard.json"

    scenario_path.write_text(
        json.dumps(
            {
                "scenarios": [
                    {
                        "id": "scenario.alpha",
                        "demo": {"entry_point": "main", "arguments": ["--demo", "sentiment"]},
                    },
                    {
                        "id": "scenario.beta",
                        "demo": {"entry_point": "main", "arguments": ["--demo", "imagination"]},
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    playlist_path.write_text(
        json.dumps(
            {
                "playlists": [
                    {
                        "id": "playlist.test",
                        "name": "Test Playlist",
                        "scenario_sequence": ["scenario.alpha", "scenario.beta"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    automation_runs_path.write_text(
        json.dumps({"last_updated": "2026-01-01T00:00:00Z", "runs": [], "schema_version": "1.0.0"}),
        encoding="utf-8",
    )

    monkeypatch.setattr(benchmarking_runner, "SCENARIO_PATH", scenario_path)
    monkeypatch.setattr(benchmarking_runner, "PLAYLIST_PATH", playlist_path)
    monkeypatch.setattr(benchmarking_runner, "EVIDENCE_DIR", evidence_dir)
    monkeypatch.setattr(benchmarking_runner, "AUTOMATION_RUNS_INDEX", automation_runs_path)
    monkeypatch.setattr(benchmarking_runner, "ROOT", tmp_path)
    monkeypatch.setattr(benchmarking_runner, "BENCHMARK_DASHBOARD_PATH", dashboard_path)

    class StubMonitor:
        def ensure_fresh(self, timeout: float = 1.5) -> TinyLlamaHealthSnapshot:  # noqa: ARG002
            return TinyLlamaHealthSnapshot(True, 200, 12, None, 0.0)

    monkeypatch.setattr(benchmarking_runner, "TinyLlamaHealthMonitor", lambda: StubMonitor())
    monkeypatch.setattr(
        benchmarking_runner.subprocess,
        "run",
        lambda *_, **__: SimpleNamespace(returncode=0, stdout="{}", stderr=""),
    )

    first_playlist_result = benchmarking_runner.run_playlist("playlist.test")
    assert first_playlist_result["playlist_id"] == "playlist.test"
    assert first_playlist_result["aggregate_metrics"]["scenario_count"] == 2
    assert first_playlist_result["aggregate_metrics"]["failures"] == 0
    assert first_playlist_result["playlist_diffs"]["baseline_artifact"] is None

    dashboard_payload = json.loads(dashboard_path.read_text(encoding="utf-8"))
    assert dashboard_payload["latest_run"]["playlist_id"] == "playlist.test"
    assert len(dashboard_payload["scenario_highlights"]) == 2
    assert dashboard_payload["coverage_snapshot"]["scenario_count"] == 2

    second_playlist_result = benchmarking_runner.run_playlist("playlist.test")
    assert second_playlist_result["playlist_id"] == "playlist.test"
    assert second_playlist_result["playlist_diffs"]["baseline_artifact"] is not None
    assert "failures" in second_playlist_result["playlist_diffs"]["aggregate_delta"]

    artifact_path = second_playlist_result["artifact_path"]
    assert artifact_path
    artifact_file = Path(tmp_path, artifact_path)
    assert artifact_file.exists()

    automation_runs = json.loads(automation_runs_path.read_text(encoding="utf-8"))
    assert len(automation_runs["runs"]) == 6, "two playlist executions (2 scenarios + aggregate each)"
    playlist_entry = automation_runs["runs"][-1]
    assert playlist_entry["run_id"].startswith("auto-0007-run-playlist")
    assert playlist_entry["evidence"]["scenario_run_ids"]
    assert playlist_entry["evidence"]["aggregate_metrics"]["scenario_count"] == 2
    assert playlist_entry["evidence"]["playlist_diffs"]["baseline_artifact"] is not None


def test_pytest_scenarios_mark_requirements_satisfied() -> None:
    scenario_result = {
        "scenario_id": "scenario.pressure_alert",
        "scenario": {
            "telemetry_requirements": [
                "pressure_alert",
                "pressure_history",
                "ledger_metadata.pressure_signal",
            ],
            "demo": {"entry_point": "pytest"},
        },
        "command_result": {"return_code": 0, "stdout_json": None},
        "health_snapshot": {"latency_ms": 0},
        "artifact_path": "logs/benchmarks/scenario.pressure_alert.json",
    }
    highlight = benchmarking_runner._build_scenario_highlight(scenario_result)
    assert highlight["coverage"]["status"] == "full"
    assert all(highlight["coverage"]["requirements"].values())


def test_hallucinator_aliases_mark_requirements_satisfied() -> None:
    stdout_json = {
        "presentation_views": [
            {"type": "hallucinator_hypothesis", "summary": "Glass city", "confidence": 0.9}
        ],
        "result_summary": {
            "outputs": [
                {
                    "hypothesis": {"summary": "Glass city"},
                    "telemetry": {
                        "health_snapshot": {
                            "is_available": True,
                            "latency_ms": 61,
                            "status_code": 200,
                        }
                    },
                }
            ]
        },
    }
    scenario_result = {
        "scenario_id": "scenario.hallucinator_imagination",
        "scenario": {
            "expected_outputs": {
                "telemetry": ["hallucinator_snapshot", "tinyllama_health_snapshot"],
            },
            "demo": {"entry_point": "main"},
        },
        "command_result": {"return_code": 0, "stdout_json": stdout_json},
        "health_snapshot": {"latency_ms": 61},
        "artifact_path": "logs/benchmarks/scenario.hallucinator_imagination.json",
    }
    highlight = benchmarking_runner._build_scenario_highlight(scenario_result)
    assert highlight["coverage"]["status"] == "full"
    assert all(highlight["coverage"]["requirements"].values())


def test_proof_prefix_requirements_use_proof_payload() -> None:
    stdout_json = {
        "result_summary": {"status": "completed", "outputs": [{"alert_count": 0}]},
        "resource_usage": {"pressure_state": {"ratio": 0.6, "status": "within_budget"}},
    }
    scenario_result = {
        "scenario_id": "scenario.sentiment_chain",
        "scenario": {
            "telemetry_requirements": [
                "proof.result_summary",
                "proof.resource_usage.pressure_state",
            ],
            "demo": {"entry_point": "main"},
        },
        "command_result": {"return_code": 0, "stdout_json": stdout_json},
        "health_snapshot": {"latency_ms": 12},
        "artifact_path": "logs/benchmarks/scenario.sentiment_chain.json",
    }
    highlight = benchmarking_runner._build_scenario_highlight(scenario_result)
    assert highlight["coverage"]["status"] == "full"
    assert all(highlight["coverage"]["requirements"].values())


def test_benchmark_dashboard_cli_renders_summary(tmp_path) -> None:
    dashboard = {
        "schema_version": "1.0.0",
        "last_updated": "2026-01-25T04:20:00Z",
        "coverage_snapshot": {
            "scenario_count": 2,
            "failing_scenarios": [],
            "pytest_targets": ["tests/test_alert_panel_tile.py::test_alert_panel_severity_order"],
            "tinyllama_latency_span_ms": 12,
        },
        "latest_run": {
            "playlist_id": "playlist.sample",
            "run_id": "auto-0007-run-playlist.sample-20260125T042000Z",
            "aggregate_metrics": {
                "scenario_count": 2,
                "failures": 0,
                "tinyllama_latency_min_ms": 45,
                "tinyllama_latency_max_ms": 57,
            },
            "diff_summary": {
                "baseline_artifact": "logs/benchmarks/playlist.sample-20260124.json",
                "aggregate_delta": {"failures": 0},
                "scenario_regressions": [],
            },
        },
        "scenario_highlights": [
            {
                "scenario_id": "scenario.sentiment",
                "run_id": "auto-0007-run-scenario.sentiment-20260125T042000Z",
                "return_code": 0,
                "coverage": {"status": "full", "requirements": {"presentation_views": True}},
                "presentation": {"view_counts": {"chain_quality": 1}},
                "tinyllama_latency_ms": 45,
            },
            {
                "scenario_id": "scenario.alerts",
                "run_id": "auto-0007-run-scenario.alerts-20260125T042010Z",
                "return_code": 0,
                "coverage": {
                    "status": "partial",
                    "requirements": {"pressure_alert": True, "pressure_history": False},
                },
                "presentation": {
                    "view_counts": {"alert_panel": 1},
                    "max_alert_severity": "warning",
                },
                "tinyllama_latency_ms": 57,
            },
        ],
    }
    rendered = benchmark_dashboard_cli.render_dashboard(dashboard)
    assert "playlist.sample" in rendered
    assert "scenario.sentiment" in rendered
    assert "pressure_history" in rendered
