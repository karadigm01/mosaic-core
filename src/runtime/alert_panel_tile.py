"""Alert panel tile that materializes pressure alerts into presentation facts."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from runtime.constraint_substrate import ConstraintFact


@dataclass(frozen=True)
class AlertPanelResult:
    fact: ConstraintFact
    alerts: List[Dict[str, object]]


class AlertPanelTile:
    """Synthesizes presentation facts describing recent pressure alerts."""

    TILE_ID = "tile.presentation.alert_panel"
    OUTPUT_TYPE = "presentation.alert_panel"
    INPUT_TYPES = ["pressure.alert_batch"]

    def execute(self, proof_id: str, alerts: List[Dict[str, object]]) -> AlertPanelResult:
        summarized = [
            {
                "signal_id": alert["signal_id"],
                "tile_id": alert["tile_id"],
                "severity": alert["severity"],
                "pressure_ratio": round(float(alert["pressure_ratio"]), 2),
            }
            for alert in alerts
        ]
        fact = ConstraintFact(
            fact_id=f"fact.alert_panel::{proof_id}",
            fact_type=self.OUTPUT_TYPE,
            payload={"alerts": summarized},
            confidence=1.0,
            ttl_seconds=300,
            provenance={
                "tile": self.TILE_ID,
                "source": "constraint_substrate.pressure_alerts",
            },
            constraints_compliance=["I1", "I2", "I3", "I4"],
        )
        return AlertPanelResult(fact, summarized)
