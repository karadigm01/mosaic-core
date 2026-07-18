from __future__ import annotations

from runtime.constraint_substrate import ConstraintFact
from runtime.pressure_summary_tile import PressureSummaryTile


def build_batch(alerts):
    return ConstraintFact(
        fact_id="pressure.alert_batch::test",
        fact_type="pressure.alert_batch",
        payload={"alerts": alerts},
        confidence=0.9,
        ttl_seconds=120,
        provenance={"source": "test"},
        constraints_compliance=["I1", "I2", "I3", "I4"],
    )


def _build_alert(*, severity: str) -> dict:
    return {
        "signal_id": f"signal::{severity}",
        "tile_id": "tile.test",
        "severity": severity,
        "pressure_ratio": 1.5,
    }


def test_pressure_summary_empty_batch() -> None:
    tile = PressureSummaryTile()
    result = tile.execute(build_batch([]))

    assert result.fact.payload == {"alert_count": 0, "severe": 0, "warnings": 0}
    assert result.work_metrics == {"alert_count": 0.0, "severe_count": 0.0}
    assert result.fact.provenance["source_fact"] == "pressure.alert_batch::test"


def test_pressure_summary_single_warning() -> None:
    tile = PressureSummaryTile()
    result = tile.execute(build_batch([_build_alert(severity="warning")]))

    assert result.fact.payload["alert_count"] == 1
    assert result.fact.payload["warnings"] == 1
    assert result.fact.payload["severe"] == 0
    assert result.work_metrics["alert_count"] == 1.0
    assert result.work_metrics["severe_count"] == 0.0


def test_pressure_summary_single_severe() -> None:
    tile = PressureSummaryTile()
    result = tile.execute(build_batch([_build_alert(severity="severe")]))

    assert result.fact.payload["severe"] == 1
    assert result.fact.payload["warnings"] == 0
    assert result.work_metrics["severe_count"] == 1.0


def test_pressure_summary_mixed_severities() -> None:
    tile = PressureSummaryTile()
    alerts = [
        _build_alert(severity="severe"),
        _build_alert(severity="warning"),
        _build_alert(severity="info"),
        _build_alert(severity="severe"),
    ]
    result = tile.execute(build_batch(alerts))

    assert result.fact.payload == {"alert_count": 4, "severe": 2, "warnings": 1}
    assert result.work_metrics == {"alert_count": 4.0, "severe_count": 2.0}


def test_pressure_summary_preserves_provenance() -> None:
    tile = PressureSummaryTile()
    batch = build_batch([_build_alert(severity="warning")])
    result = tile.execute(batch)

    assert result.fact.provenance == {
        "tile": PressureSummaryTile.TILE_ID,
        "source_fact": batch.fact_id,
    }
    assert result.fact.fact_id == f"pressure.summary::{batch.fact_id}"
    assert result.fact.fact_type == PressureSummaryTile.OUTPUT_TYPE


def test_pressure_summary_deterministic_metrics() -> None:
    tile = PressureSummaryTile()
    batch = build_batch([
        _build_alert(severity="severe"),
        _build_alert(severity="warning"),
        _build_alert(severity="warning"),
    ])
    result_a = tile.execute(batch)
    result_b = tile.execute(batch)

    assert result_a.fact.payload == result_b.fact.payload
    assert result_a.work_metrics == result_b.work_metrics
