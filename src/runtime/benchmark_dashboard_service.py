"""Lightweight HTTP service exposing benchmarking dashboard data."""
from __future__ import annotations

import argparse
import json
import logging
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from runtime import benchmark_operations, benchmarking_runner, macro_tile_generator

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DASHBOARD_PATH = ROOT / "ai_docs" / "benchmarking_dashboard.json"
DEFAULT_HISTORY_DIR = ROOT / "logs" / "benchmarks" / "history"
DEFAULT_KB_INDEX_PATH = ROOT / "knowledge_base" / "kb_index.json"
DEFAULT_COMPONENT_INDEX_PATH = ROOT / "ai_docs" / "component_index.json"
MACRO_CATALOG_PATH = (ROOT / macro_tile_generator.DEFAULT_CATALOG_PATH).resolve()
MACRO_SCHEMA_PATH = (ROOT / macro_tile_generator.DEFAULT_SCHEMA_PATH).resolve()
MACRO_MODULE_DIR = (ROOT / macro_tile_generator.DEFAULT_MODULE_DIR).resolve()
MACRO_DOC_DIR = (ROOT / macro_tile_generator.DEFAULT_DOC_DIR).resolve()
MACRO_TEST_DIR = (ROOT / macro_tile_generator.DEFAULT_TEST_DIR).resolve()
MACRO_PATCH_DIR = (ROOT / macro_tile_generator.DEFAULT_PATCH_DIR).resolve()
VALID_LIFECYCLE_STATES = {"proposed", "sandboxed", "promoted"}
LOG = logging.getLogger(__name__)


class BenchmarkDashboardDataSource:
    """Loads dashboard, history, and health metadata for the service."""

    def __init__(
        self,
        dashboard_path: Path = DEFAULT_DASHBOARD_PATH,
        history_dir: Path = DEFAULT_HISTORY_DIR,
        kb_index_path: Path = DEFAULT_KB_INDEX_PATH,
    ) -> None:
        self.dashboard_path = Path(dashboard_path)
        self.history_dir = Path(history_dir)
        self.kb_index_path = Path(kb_index_path)

    def load_dashboard(self) -> Dict[str, Any]:
        if not self.dashboard_path.exists():
            raise FileNotFoundError(f"dashboard file not found: {self.dashboard_path}")
        return json.loads(self.dashboard_path.read_text(encoding="utf-8"))

    def _load_kb_snapshot(self) -> Dict[str, Any]:
        if not self.kb_index_path.exists():
            LOG.warning("kb_index.json missing at %s", self.kb_index_path)
            return {}
        data = json.loads(self.kb_index_path.read_text(encoding="utf-8"))
        return data.get("latest_tinyllama_health_snapshot", {})

    def list_history(
        self,
        limit: Optional[int] = None,
        include_payload: bool = False,
    ) -> List[Dict[str, Any]]:
        if not self.history_dir.exists():
            return []
        files = sorted(
            self.history_dir.glob("dashboard.*.json"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        if limit is not None:
            files = files[:limit]
        entries: List[Dict[str, Any]] = []
        for path in files:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                LOG.warning("history file %s is not valid JSON: %s", path, exc)
                continue
            entry = self._summarize_history_entry(path, payload, include_payload)
            entries.append(entry)
        return entries

    def build_state(
        self,
        history_limit: int = 5,
        include_history_payload: bool = False,
    ) -> Dict[str, Any]:
        dashboard = self.load_dashboard()
        history = self.list_history(history_limit, include_history_payload)
        snapshot = self._load_kb_snapshot()
        return {
            "dashboard": dashboard,
            "history": history,
            "tinyllama_health": snapshot,
            "source_paths": {
                "dashboard": str(self.dashboard_path),
                "history_dir": str(self.history_dir),
                "kb_index": str(self.kb_index_path),
            },
        }

    def _summarize_history_entry(
        self,
        path: Path,
        payload: Dict[str, Any],
        include_payload: bool,
    ) -> Dict[str, Any]:
        latest = payload.get("latest_run", {})
        coverage = payload.get("coverage_snapshot", {})
        summary = {
            "path": self._relativize(path),
            "last_updated": payload.get("last_updated"),
            "playlist_id": latest.get("playlist_id"),
            "run_id": latest.get("run_id"),
            "scenario_count": coverage.get("scenario_count", len(payload.get("scenario_highlights", []))),
            "coverage_status": self._coverage_status(payload),
        }
        if include_payload:
            summary["payload"] = payload
        return summary

    @staticmethod
    def _coverage_status(payload: Dict[str, Any]) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for highlight in payload.get("scenario_highlights", []):
            status = highlight.get("coverage", {}).get("status", "unknown")
            counts[status] = counts.get(status, 0) + 1
        return counts

    @staticmethod
    def _relativize(path: Path) -> str:
        try:
            return str(path.relative_to(ROOT))
        except ValueError:
            return str(path)


class BenchmarkDashboardRequestHandler(BaseHTTPRequestHandler):
    data_source: BenchmarkDashboardDataSource

    def do_GET(self) -> None:  # noqa: N802 - http method signature
        parsed = urlparse(self.path)
        if parsed.path == "/healthz":
            self._write_json(HTTPStatus.OK, {"status": "ok"})
            return
        if parsed.path == "/api/dashboard":
            params = parse_qs(parsed.query)
            history_limit = self._int_param(params.get("history_limit", ["5"])[0], default=5)
            include_payload = params.get("include_payload", ["0"])[0] == "1"
            try:
                state = self.data_source.build_state(history_limit, include_payload)
            except FileNotFoundError as exc:
                self._write_json(HTTPStatus.NOT_FOUND, {"error": str(exc)})
                return
            state["operations"] = benchmark_operations.load_summary()
            self._write_json(HTTPStatus.OK, state)
            return
        if parsed.path == "/api/macro_tiles/catalog":
            self._handle_macro_catalog()
            return
        if parsed.path == "/api/artifact":
            self._handle_artifact(parsed.query)
            return
        if parsed.path == "/":
            self._write_json(
                HTTPStatus.OK,
                {
                    "message": "Benchmark dashboard service",
                    "endpoints": ["/api/dashboard", "/healthz"],
                },
            )
            return
        self._write_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802 - http method signature
        parsed = urlparse(self.path)
        if parsed.path == "/api/replay":
            self._handle_replay()
            return
        if parsed.path == "/api/remediation":
            self._handle_remediation()
            return
        if parsed.path == "/api/macro_tiles":
            self._handle_macro_tile()
            return
        self._write_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: D401 - match signature
        LOG.info("dashboard_service: " + fmt, *args)

    def _write_json(self, status: HTTPStatus, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    @staticmethod
    def _int_param(raw: str, default: int) -> int:
        try:
            value = int(raw)
            if value < 0:
                return default
            return value
        except (TypeError, ValueError):
            return default

    def _read_json_body(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(length) if length > 0 else b""
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("invalid_json") from exc

    def _handle_replay(self) -> None:
        try:
            body = self._read_json_body()
        except ValueError:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "invalid_json"})
            return
        scenario_id = (body.get("scenario_id") or "").strip()
        if not scenario_id:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "scenario_id_required"})
            return
        try:
            evidence = benchmarking_runner.run_scenario(scenario_id)
        except ValueError as exc:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        except Exception:
            LOG.exception("Failed to replay scenario %s", scenario_id)
            self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "replay_failed"})
            return
        replay_entry = benchmark_operations.record_replay_event(
            scenario_id,
            evidence.get("run_id"),
            evidence.get("artifact_path"),
            (evidence.get("command_result") or {}).get("return_code"),
        )
        summary = benchmark_operations.load_summary()
        self._write_json(
            HTTPStatus.OK,
            {
                "status": "ok",
                "replay": replay_entry,
                "run_id": evidence.get("run_id"),
                "artifact_path": evidence.get("artifact_path"),
                "operations": summary,
            },
        )

    def _handle_remediation(self) -> None:
        try:
            body = self._read_json_body()
        except ValueError:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "invalid_json"})
            return
        scenario_id = (body.get("scenario_id") or "").strip()
        action = (body.get("action") or "").strip()
        if not scenario_id or not action:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "scenario_id_and_action_required"})
            return
        if action not in {"open_task", "pytest_subset"}:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "unsupported_action"})
            return
        if action == "open_task":
            entry = benchmark_operations.record_remediation_event(
                scenario_id,
                action,
                status="open",
                details={"reason": body.get("reason")},
            )
            summary = benchmark_operations.load_summary()
            self._write_json(HTTPStatus.OK, {"status": "ok", "remediation": entry, "operations": summary})
            return
        try:
            evidence = benchmarking_runner.run_scenario(scenario_id)
        except ValueError as exc:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        except Exception:
            LOG.exception("Failed remediation pytest for %s", scenario_id)
            self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "remediation_failed"})
            return
        return_code = (evidence.get("command_result") or {}).get("return_code")
        status = "closed" if return_code == 0 else "needs_follow_up"
        entry = benchmark_operations.record_remediation_event(
            scenario_id,
            action,
            status=status,
            details={
                "run_id": evidence.get("run_id"),
                "artifact_path": evidence.get("artifact_path"),
                "return_code": return_code,
            },
        )
        summary = benchmark_operations.load_summary()
        self._write_json(
            HTTPStatus.OK,
            {
                "status": "ok",
                "remediation": entry,
                "operations": summary,
            },
        )

    def _handle_artifact(self, query: str) -> None:
        params = parse_qs(query)
        raw_path = (params.get("path", [""])[0] or "").strip()
        if not raw_path:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "path_required"})
            return
        try:
            artifact_path = self._resolve_artifact_path(raw_path)
        except ValueError:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "forbidden_path"})
            return
        if not artifact_path.exists() or not artifact_path.is_file():
            self._write_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        try:
            text = artifact_path.read_text(encoding="utf-8")
        except OSError as exc:
            LOG.error("Failed to read artifact %s: %s", artifact_path, exc)
            self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "read_failed"})
            return
        payload: Dict[str, Any] = {
            "path": self.data_source._relativize(artifact_path),
            "text": text,
        }
        try:
            payload["payload"] = json.loads(text)
        except json.JSONDecodeError:
            pass
        self._write_json(HTTPStatus.OK, payload)

    def _handle_macro_catalog(self) -> None:
        try:
            catalog = macro_tile_generator.load_tile_catalog(MACRO_CATALOG_PATH)
        except FileNotFoundError:
            self._write_json(HTTPStatus.NOT_FOUND, {"error": "catalog_missing"})
            return
        tiles = []
        for spec in catalog.values():
            tiles.append(
                {
                    "tile_id": spec.tile_id,
                    "tile_name": spec.tile_name or spec.tile_id,
                    "capability": spec.capabilities[0] if spec.capabilities else None,
                    "lifecycle_state": spec.lifecycle_state,
                    "inputs": spec.input_types,
                    "outputs": spec.output_types,
                }
            )
        self._write_json(HTTPStatus.OK, {"tiles": tiles})

    def _handle_macro_tile(self) -> None:
        try:
            body = self._read_json_body()
        except ValueError:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "invalid_json"})
            return
        tile_id = (body.get("tile_id") or "").strip()
        tile_name = (body.get("tile_name") or "").strip()
        plan_raw = body.get("plan")
        generated_by = (body.get("generated_by") or "dashboard_service").strip()
        lifecycle_state = (body.get("lifecycle_state") or "proposed").strip().lower()
        register_component = bool(body.get("register_component"))
        if lifecycle_state not in VALID_LIFECYCLE_STATES:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "invalid_lifecycle_state"})
            return
        if register_component and lifecycle_state != "promoted":
            self._write_json(
                HTTPStatus.BAD_REQUEST,
                {"error": "register_component requires lifecycle_state=promoted"},
            )
            return
        if not tile_id or not tile_name:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "tile_id_and_tile_name_required"})
            return
        if not isinstance(plan_raw, list):
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "plan_list_required"})
            return
        plan = [str(item).strip() for item in plan_raw if str(item).strip()]
        if len(plan) < 2:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "plan_must_include_at_least_two_tiles"})
            return
        try:
            artifacts = macro_tile_generator.generate_macro_tile(
                tile_id=tile_id,
                tile_name=tile_name,
                plan_tile_ids=plan,
                catalog_path=MACRO_CATALOG_PATH,
                schema_path=MACRO_SCHEMA_PATH,
                module_dir=MACRO_MODULE_DIR,
                doc_dir=MACRO_DOC_DIR,
                test_dir=MACRO_TEST_DIR,
                patch_dir=MACRO_PATCH_DIR,
                generated_by=generated_by,
                timestamp=body.get("timestamp"),
                lifecycle_state=lifecycle_state,
            )
        except ValueError as exc:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        except Exception:
            LOG.exception("macro tile generation failed for %s", tile_id)
            self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "macro_generation_failed"})
            return
        response: Dict[str, Any] = {
            "status": "ok",
            "artifacts": {
                label: self.data_source._relativize(path)
                for label, path in artifacts.items()
            },
            "lifecycle_state": lifecycle_state,
        }
        if register_component:
            try:
                macro_tile_generator.register_macro_tile_doc(
                    artifacts["doc"],
                    DEFAULT_COMPONENT_INDEX_PATH,
                    ROOT,
                )
            except ValueError as exc:
                self._write_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            except Exception:
                LOG.exception("macro tile registration failed for %s", tile_id)
                self._write_json(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    {"error": "macro_registration_failed"},
                )
                return
            response["component_registered"] = True
            response["component_index_path"] = self.data_source._relativize(DEFAULT_COMPONENT_INDEX_PATH)
        else:
            response["component_registered"] = False
        self._write_json(HTTPStatus.OK, response)

    def _resolve_artifact_path(self, raw_path: str) -> Path:
        candidate = Path(raw_path)
        if not candidate.is_absolute():
            candidate = ROOT / candidate
        resolved = candidate.resolve()
        allowed_roots = {
            ROOT.resolve(),
            self.data_source.dashboard_path.parent.resolve(),
            self.data_source.history_dir.resolve(),
            self.data_source.kb_index_path.parent.resolve(),
            benchmark_operations.OPERATIONS_DIR.resolve(),
        }
        if not any(self._is_within(resolved, root) for root in allowed_roots):
            raise ValueError("outside_root")
        return resolved

    @staticmethod
    def _is_within(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False


def _make_handler(data_source: BenchmarkDashboardDataSource):
    class Handler(BenchmarkDashboardRequestHandler):
        pass

    Handler.data_source = data_source
    return Handler


def run_server(host: str, port: int, data_source: BenchmarkDashboardDataSource) -> ThreadingHTTPServer:
    handler_cls = _make_handler(data_source)
    server = ThreadingHTTPServer((host, port), handler_cls)
    thread = threading.Thread(target=server.serve_forever, name="benchmark-dashboard-server", daemon=True)
    thread.start()
    LOG.info("dashboard service running on %s:%s", host, server.server_port)
    return server


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Serve benchmarking dashboard data")
    parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8080, help="Port to bind (default: 8080)")
    parser.add_argument("--dashboard-path", type=Path, default=DEFAULT_DASHBOARD_PATH)
    parser.add_argument("--history-dir", type=Path, default=DEFAULT_HISTORY_DIR)
    parser.add_argument("--kb-index-path", type=Path, default=DEFAULT_KB_INDEX_PATH)
    parser.add_argument(
        "--history-limit", type=int, default=5, help="History entries to include in default payload"
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    data_source = BenchmarkDashboardDataSource(
        dashboard_path=args.dashboard_path,
        history_dir=args.history_dir,
        kb_index_path=args.kb_index_path,
    )
    server = run_server(args.host, args.port, data_source)
    try:
        thread = threading.Event()
        thread.wait()
    except KeyboardInterrupt:
        LOG.info("shutting down dashboard service")
        server.shutdown()


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    main()
