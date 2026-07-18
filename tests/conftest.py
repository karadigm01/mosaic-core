"""Pytest configuration ensuring runtime package is discoverable."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if SRC_PATH.exists() and str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

import pytest

from runtime.tinyllama_health import TinyLlamaHealthMonitor, TinyLlamaHealthSnapshot

_HEALTH_MONITOR = TinyLlamaHealthMonitor()


@pytest.fixture(scope="session")
def tinyllama_health_snapshot() -> TinyLlamaHealthSnapshot:
    """Single health probe reused across integration tests."""

    return _HEALTH_MONITOR.ensure_fresh(timeout=1.0)
