import json
import socket
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict

import pytest

from runtime import benchmark_dashboard_service, benchmark_operations, macro_tile_generator


@pytest.fixture()
def sample_files(tmp_path: Path) -> dict:
    dashboard = tmp_path / "ai_docs" / "benchmarking_dashboard.json"
    dashboard.parent.mkdir(parents=True)
    history_dir = tmp_path / "logs" / "benchmarks" / "history"
    history_dir.mkdir(parents=True)
    kb_index = tmp_path / "knowledge_base" / "kb_index.json"
    kb_index.parent.mkdir(parents=True)

    dashboard_payload = {
        "last_updated": "2026-01-25T06:27:49Z",
        "latest_run": {
            "playlist_id": "playlist.phase3_regression",
            "run_id": "run-latest",
        },
        "coverage_snapshot": {"scenario_count": 2},
        "scenario_highlights": [
            {"scenario_id": "scenario.a", "coverage": {"status": "full"}},
            {"scenario_id": "scenario.b", "coverage": {"status": "missing"}},
        ],
    }
    dashboard.write_text(json.dumps(dashboard_payload), encoding="utf-8")

    history_payload = dashboard_payload.copy()
    history_payload["latest_run"] = {"playlist_id": "playlist.phase3_observability", "run_id": "run-history"}
    history_payload["scenario_highlights"] = [
        {"scenario_id": "scenario.c", "coverage": {"status": "full"}},
    ]
    history_path = history_dir / "dashboard.playlist.phase3_observability-run-history.json"
    history_path.write_text(json.dumps(history_payload), encoding="utf-8")

    kb_index_payload = {
        "latest_tinyllama_health_snapshot": {"status_code": 200, "latency_ms": 1}
    }
    kb_index.write_text(json.dumps(kb_index_payload), encoding="utf-8")

    return {
        "dashboard": dashboard,
        "history_dir": history_dir,
        "kb_index": kb_index,
    }


def test_datasource_build_state(sample_files: dict) -> None:
    source = benchmark_dashboard_service.BenchmarkDashboardDataSource(
        dashboard_path=sample_files["dashboard"],
        history_dir=sample_files["history_dir"],
        kb_index_path=sample_files["kb_index"],
    )
    state = source.build_state(history_limit=1)
    assert state["dashboard"]["latest_run"]["run_id"] == "run-latest"
    assert state["history"][0]["playlist_id"] == "playlist.phase3_observability"
    assert state["tinyllama_health"]["latency_ms"] == 1


def _find_free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    addr, port = sock.getsockname()
    sock.close()
    return port


def test_http_endpoint_returns_state(sample_files: dict) -> None:
    port = _find_free_port()
    source = benchmark_dashboard_service.BenchmarkDashboardDataSource(
        dashboard_path=sample_files["dashboard"],
        history_dir=sample_files["history_dir"],
        kb_index_path=sample_files["kb_index"],
    )
    server = benchmark_dashboard_service.run_server("127.0.0.1", port, source)
    try:
        # give server a moment to start
        time.sleep(0.1)
        with urllib.request.urlopen(f"http://127.0.0.1:{server.server_port}/api/dashboard") as response:
            payload = json.loads(response.read().decode("utf-8"))
        assert payload["dashboard"]["latest_run"]["run_id"] == "run-latest"
        assert payload["history"], "expected history entries"
    finally:
        server.shutdown()
        # ensure threads exit cleanly
        time.sleep(0.05)


@pytest.fixture()
def operations_logs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    replay_path = tmp_path / "replay_events.json"
    remediation_path = tmp_path / "remediation_events.json"
    monkeypatch.setattr(benchmark_operations, "REPLAY_LOG_PATH", replay_path)
    monkeypatch.setattr(benchmark_operations, "REMEDIATION_LOG_PATH", remediation_path)
    return {"replay": replay_path, "remediation": remediation_path}


def _post_json(url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read().decode("utf-8"))


def test_post_replay_records_event(sample_files: dict, operations_logs: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    port = _find_free_port()
    source = benchmark_dashboard_service.BenchmarkDashboardDataSource(
        dashboard_path=sample_files["dashboard"],
        history_dir=sample_files["history_dir"],
        kb_index_path=sample_files["kb_index"],
    )
    fake_result = {
        "scenario_id": "scenario.a",
        "run_id": "auto-0007-run-scenario.a-1",
        "artifact_path": "logs/benchmarks/scenario.a-1.json",
        "command_result": {"return_code": 0},
    }
    monkeypatch.setattr(
        benchmark_dashboard_service.benchmarking_runner,
        "run_scenario",
        lambda scenario_id: fake_result,
    )
    server = benchmark_dashboard_service.run_server("127.0.0.1", port, source)
    try:
        time.sleep(0.1)
        payload = _post_json(
            f"http://127.0.0.1:{server.server_port}/api/replay",
            {"scenario_id": "scenario.a"},
        )
        assert payload["status"] == "ok"
        assert payload["operations"]["replay_count"] == 1
        assert benchmark_operations.REPLAY_LOG_PATH.exists()
    finally:
        server.shutdown()
        time.sleep(0.05)


def test_post_remediation_open_task_tracks_backlog(
    sample_files: dict,
    operations_logs: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    port = _find_free_port()
    source = benchmark_dashboard_service.BenchmarkDashboardDataSource(
        dashboard_path=sample_files["dashboard"],
        history_dir=sample_files["history_dir"],
        kb_index_path=sample_files["kb_index"],
    )
    server = benchmark_dashboard_service.run_server("127.0.0.1", port, source)
    try:
        time.sleep(0.1)
        payload = _post_json(
            f"http://127.0.0.1:{server.server_port}/api/remediation",
            {"scenario_id": "scenario.a", "action": "open_task", "reason": "triage"},
        )
        assert payload["status"] == "ok"
        assert payload["operations"]["remediation_backlog"] == 1
    finally:
        server.shutdown()
        time.sleep(0.05)


def test_post_remediation_pytest_runs_scenario(
    sample_files: dict,
    operations_logs: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    port = _find_free_port()
    source = benchmark_dashboard_service.BenchmarkDashboardDataSource(
        dashboard_path=sample_files["dashboard"],
        history_dir=sample_files["history_dir"],
        kb_index_path=sample_files["kb_index"],
    )
    fake_result = {
        "scenario_id": "scenario.a",
        "run_id": "auto-0007-run-scenario.a-2",
        "artifact_path": "logs/benchmarks/scenario.a-2.json",
        "command_result": {"return_code": 0},
    }
    called: Dict[str, Any] = {}

    def _fake_run(scenario_id: str) -> Dict[str, Any]:
        called["scenario_id"] = scenario_id
        return fake_result

    monkeypatch.setattr(benchmark_dashboard_service.benchmarking_runner, "run_scenario", _fake_run)
    server = benchmark_dashboard_service.run_server("127.0.0.1", port, source)
    try:
        time.sleep(0.1)
        payload = _post_json(
            f"http://127.0.0.1:{server.server_port}/api/remediation",
            {"scenario_id": "scenario.a", "action": "pytest_subset"},
        )
        assert payload["status"] == "ok"
        assert called["scenario_id"] == "scenario.a"
        assert payload["remediation"]["status"] == "closed"
    finally:
        server.shutdown()
        time.sleep(0.05)


def test_get_macro_catalog_returns_promoted_tiles(
    sample_files: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    port = _find_free_port()
    source = benchmark_dashboard_service.BenchmarkDashboardDataSource(
        dashboard_path=sample_files["dashboard"],
        history_dir=sample_files["history_dir"],
        kb_index_path=sample_files["kb_index"],
    )
    spec = macro_tile_generator.TileSpec(
        tile_id="tile.lang.semantic_router",
        capabilities=["conversation.route"],
        inputs=[{"fact_type": "conversation.turn"}],
        outputs=[{"fact_type": "conversation.route_decision"}],
        behavior_guarantees={},
        resource_budget={},
        presentation_manifest={},
        lifecycle_state="promoted",
        constraints_compliance=["I1"],
    )
    monkeypatch.setattr(
        benchmark_dashboard_service.macro_tile_generator,
        "load_tile_catalog",
        lambda path: {spec.tile_id: spec},
    )
    server = benchmark_dashboard_service.run_server("127.0.0.1", port, source)
    try:
        time.sleep(0.1)
        with urllib.request.urlopen(
            f"http://127.0.0.1:{server.server_port}/api/macro_tiles/catalog"
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
        assert payload["tiles"][0]["tile_id"] == spec.tile_id
        assert payload["tiles"][0]["inputs"] == spec.input_types
    finally:
        server.shutdown()
        time.sleep(0.05)


def test_post_macro_tile_generates_artifacts(
    sample_files: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    port = _find_free_port()
    source = benchmark_dashboard_service.BenchmarkDashboardDataSource(
        dashboard_path=sample_files["dashboard"],
        history_dir=sample_files["history_dir"],
        kb_index_path=sample_files["kb_index"],
    )
    artifacts = {
        "module": Path("src/runtime/synthesized_tiles/demo.py"),
        "doc": Path("ai_docs/synthesized_tiles/demo.json"),
        "test": Path("tests/synthesized_tiles/test_demo.py"),
        "registry_patch": Path("ai_docs/synthesized_tiles/registry_patches/demo.json"),
    }
    called: dict = {}

    def _fake_generate(**kwargs):
        called["kwargs"] = kwargs
        return artifacts

    monkeypatch.setattr(benchmark_dashboard_service.macro_tile_generator, "generate_macro_tile", _fake_generate)
    monkeypatch.setattr(
        benchmark_dashboard_service.macro_tile_generator,
        "register_macro_tile_doc",
        lambda *args, **kwargs: None,
    )
    server = benchmark_dashboard_service.run_server("127.0.0.1", port, source)
    try:
        time.sleep(0.1)
        payload = _post_json(
            f"http://127.0.0.1:{server.server_port}/api/macro_tiles",
            {
                "tile_id": "tile.macro.demo",
                "tile_name": "Demo Macro",
                "plan": ["tile.lang.semantic_router", "tile.reasoning.route_dispatch"],
                "lifecycle_state": "proposed",
            },
        )
        assert payload["status"] == "ok"
        assert payload["component_registered"] is False
        assert called["kwargs"]["plan_tile_ids"] == [
            "tile.lang.semantic_router",
            "tile.reasoning.route_dispatch",
        ]
    finally:
        server.shutdown()
        time.sleep(0.05)


def test_post_macro_tile_registers_when_promoted(
    sample_files: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    port = _find_free_port()
    source = benchmark_dashboard_service.BenchmarkDashboardDataSource(
        dashboard_path=sample_files["dashboard"],
        history_dir=sample_files["history_dir"],
        kb_index_path=sample_files["kb_index"],
    )
    artifacts = {
        "module": Path("src/runtime/synthesized_tiles/demo.py"),
        "doc": Path("ai_docs/synthesized_tiles/demo.json"),
        "test": Path("tests/synthesized_tiles/test_demo.py"),
        "registry_patch": Path("ai_docs/synthesized_tiles/registry_patches/demo.json"),
    }
    monkeypatch.setattr(
        benchmark_dashboard_service.macro_tile_generator,
        "generate_macro_tile",
        lambda **kwargs: artifacts,
    )
    called: dict = {}

    def _fake_register(doc_path: Path, index_path: Path, workspace_root: Path) -> None:
        called["args"] = (doc_path, index_path, workspace_root)

    monkeypatch.setattr(
        benchmark_dashboard_service.macro_tile_generator,
        "register_macro_tile_doc",
        _fake_register,
    )
    server = benchmark_dashboard_service.run_server("127.0.0.1", port, source)
    try:
        time.sleep(0.1)
        payload = _post_json(
            f"http://127.0.0.1:{server.server_port}/api/macro_tiles",
            {
                "tile_id": "tile.macro.demo",
                "tile_name": "Demo Macro",
                "plan": ["tile.lang.semantic_router", "tile.reasoning.route_dispatch"],
                "lifecycle_state": "promoted",
                "register_component": True,
            },
        )
        assert payload["component_registered"] is True
        assert called["args"][0] == artifacts["doc"]
    finally:
        server.shutdown()
        time.sleep(0.05)


def test_post_macro_tile_rejects_register_without_promotion(
    sample_files: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    port = _find_free_port()
    source = benchmark_dashboard_service.BenchmarkDashboardDataSource(
        dashboard_path=sample_files["dashboard"],
        history_dir=sample_files["history_dir"],
        kb_index_path=sample_files["kb_index"],
    )
    monkeypatch.setattr(
        benchmark_dashboard_service.macro_tile_generator,
        "generate_macro_tile",
        lambda **kwargs: {
            "module": Path("src/demo.py"),
            "doc": Path("ai_docs/demo.json"),
            "test": Path("tests/demo.py"),
            "registry_patch": Path("ai_docs/demo_patch.json"),
        },
    )
    server = benchmark_dashboard_service.run_server("127.0.0.1", port, source)
    try:
        time.sleep(0.1)
        with pytest.raises(urllib.error.HTTPError):
            _post_json(
                f"http://127.0.0.1:{server.server_port}/api/macro_tiles",
                {
                    "tile_id": "tile.macro.demo",
                    "tile_name": "Demo Macro",
                    "plan": ["tile.lang.semantic_router", "tile.reasoning.route_dispatch"],
                    "lifecycle_state": "sandboxed",
                    "register_component": True,
                },
            )
    finally:
        server.shutdown()
        time.sleep(0.05)
