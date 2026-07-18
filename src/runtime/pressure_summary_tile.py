"""Pressure summary tile that condenses alert batches into goal facts."""
from __future__ import annotations

from typing import Dict, List

from runtime.constraint_substrate import ConstraintFact
from runtime.semantic_router import TileExecutionResult


class PressureSummaryTile:
    """Produces aggregate pressure summaries for downstream consumers."""

    TILE_ID = "tile.reasoning.pressure_summary"
    INPUT_TYPES = ["pressure.alert_batch"]
    OUTPUT_TYPE = "pressure.summary"

    def execute(self, alert_batch: ConstraintFact) -> TileExecutionResult:
        alerts: List[Dict[str, object]] = list(alert_batch.payload.get("alerts", []))
        severe = sum(1 for alert in alerts if alert.get("severity") == "severe")
        warnings = sum(1 for alert in alerts if alert.get("severity") == "warning")
        summary_fact = ConstraintFact(
            fact_id=f"pressure.summary::{alert_batch.fact_id}",
            fact_type=self.OUTPUT_TYPE,
            payload={
                "alert_count": len(alerts),
                "severe": severe,
                "warnings": warnings,
            },
            confidence=alert_batch.confidence,
            ttl_seconds=alert_batch.ttl_seconds,
            provenance={
                "tile": self.TILE_ID,
                "source_fact": alert_batch.fact_id,
            },
            constraints_compliance=alert_batch.constraints_compliance,
        )
        metrics = {
            "alert_count": float(len(alerts)),
            "severe_count": float(severe),
        }
        return TileExecutionResult(summary_fact, metrics)
