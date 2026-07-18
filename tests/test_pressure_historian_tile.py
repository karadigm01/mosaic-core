from __future__ import annotations

from runtime.constraint_substrate import ConstraintFact
from runtime.pressure_historian_tile import PressureHistorianTile


def _collection_fact(signals):
    return ConstraintFact(
        fact_id="pressure.signal_collection::proof::demo",
        fact_type="pressure.signal_collection",
        payload={"proof_id": "proof::demo", "signals": signals},
        confidence=1.0,
        ttl_seconds=600,
        provenance={"source": "test"},
        constraints_compliance=["I1", "I2", "I3", "I4"],
    )


def test_pressure_historian_reports_stable_trend() -> None:
    tile = PressureHistorianTile()
    fact = _collection_fact(
        [
            {"tile_id": "tile.a", "pressure_ratio": 0.8, "severity": "info"},
            {"tile_id": "tile.b", "pressure_ratio": 0.9, "severity": "info"},
        ]
    )

    result = tile.execute(fact)

    assert result.fact.payload["trend"] == "stable"
    assert result.fact.payload["signal_count"] == 2
    assert result.fact.payload["tile_occurrences"] == {"tile.a": 1, "tile.b": 1}
    assert result.work_metrics["signal_count"] == 2.0


def test_pressure_historian_flags_critical_trend() -> None:
    tile = PressureHistorianTile()
    fact = _collection_fact(
        [
            {"tile_id": "tile.a", "pressure_ratio": 3.4, "severity": "severe"},
            {"tile_id": "tile.b", "pressure_ratio": 2.2, "severity": "warning"},
        ]
    )

    result = tile.execute(fact)

    assert result.fact.payload["trend"] == "critical"
    assert result.fact.payload["severity_counts"]["severe"] == 1
    assert result.fact.payload["max_ratio"] >= 3.0


def test_pressure_historian_is_deterministic() -> None:
    tile = PressureHistorianTile()
    fact = _collection_fact([
        {"tile_id": "tile.a", "pressure_ratio": 1.8, "severity": "warning"},
        {"tile_id": "tile.a", "pressure_ratio": 1.7, "severity": "warning"},
    ])

    first = tile.execute(fact)
    second = tile.execute(fact)

    assert first.fact.payload == second.fact.payload
    assert first.work_metrics == second.work_metrics
