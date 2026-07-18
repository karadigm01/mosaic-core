"""TinyLLaMA health telemetry utilities."""
from __future__ import annotations

import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Optional

_DEFAULT_HEALTH_URL = os.environ.get("TINYLLAMA_HEALTH_URL", "http://127.0.0.1:8088/v1/models")


@dataclass
class TinyLlamaHealthSnapshot:
    """Represents the outcome of a TinyLLaMA health probe."""

    is_available: bool
    status_code: Optional[int]
    latency_ms: Optional[int]
    failure_reason: Optional[str]
    probed_at: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_available": self.is_available,
            "status_code": self.status_code,
            "latency_ms": self.latency_ms,
            "failure_reason": self.failure_reason,
            "probed_at": self.probed_at,
        }


class TinyLlamaHealthMonitor:
    """Lightweight probe manager with cached snapshots."""

    def __init__(self, health_url: str = _DEFAULT_HEALTH_URL, ttl_seconds: int = 60) -> None:
        self._health_url = health_url
        self._ttl_seconds = ttl_seconds
        self._latest: Optional[TinyLlamaHealthSnapshot] = None

    def latest(self) -> TinyLlamaHealthSnapshot:
        if self._latest is None:
            return TinyLlamaHealthSnapshot(False, None, None, "not_probed", 0.0)
        return self._latest

    def ensure_fresh(self, timeout: float = 1.0) -> TinyLlamaHealthSnapshot:
        snapshot = self._latest
        if snapshot and (time.time() - snapshot.probed_at) < self._ttl_seconds:
            return snapshot
        return self.probe(timeout)

    def probe(self, timeout: float = 1.0) -> TinyLlamaHealthSnapshot:
        start = time.perf_counter()
        try:
            with urllib.request.urlopen(self._health_url, timeout=timeout) as response:
                latency_ms = int((time.perf_counter() - start) * 1000)
                status_code = getattr(response, "status", 200)
                snapshot = TinyLlamaHealthSnapshot(True, status_code, latency_ms, None, time.time())
        except (urllib.error.URLError, OSError) as exc:
            latency_ms = int((time.perf_counter() - start) * 1000)
            snapshot = TinyLlamaHealthSnapshot(False, None, latency_ms, str(exc), time.time())
        self._latest = snapshot
        return snapshot


DEFAULT_MONITOR = TinyLlamaHealthMonitor()
