"""Route dispatch tile that transforms route decisions into pressure alerts."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from runtime.constraint_substrate import ConstraintFact
from runtime.semantic_router import SemanticRouterTile, TileExecutionResult


@dataclass(frozen=True)
class DispatchTarget:
    tile_id: str
    base_ratio: float
    max_ratio: float


class RouteDispatchTile:
    """Generates deterministic pressure alerts for downstream presentation tiles."""

    TILE_ID = "tile.reasoning.route_dispatch"
    OUTPUT_TYPE = "pressure.alert_batch"
    INPUT_TYPES = [SemanticRouterTile.OUTPUT_TYPE]

    _ROUTE_DISPATCH_MAP: Dict[str, List[DispatchTarget]] = {
        "route.weather": [
            DispatchTarget("tile.weather.forecaster", 1.3, 2.1),
            DispatchTarget("tile.presentation.alert_panel", 0.8, 1.2),
        ],
        "route.news": [
            DispatchTarget("tile.news.digest", 1.1, 1.6),
        ],
        "route.support": [
            DispatchTarget("tile.support.agent", 2.2, 3.0),
            DispatchTarget("tile.presentation.alert_panel", 1.4, 2.4),
        ],
        "route.handoff.human": [
            DispatchTarget("tile.support.triage", 1.0, 1.0),
        ],
        "route.imagination": [
            DispatchTarget("tile.lang.guided_hallucinator", 1.6, 2.3),
            DispatchTarget("tile.presentation.alert_panel", 1.1, 1.8),
        ],
    }

    def execute(self, route_fact: ConstraintFact) -> TileExecutionResult:
        route_id = str(route_fact.payload.get("route_id", "route.unknown"))
        targets = self._ROUTE_DISPATCH_MAP.get(route_id, self._ROUTE_DISPATCH_MAP["route.handoff.human"])
        alerts = [
            self._build_alert(route_fact, target, idx)
            for idx, target in enumerate(targets)
        ]
        fact = ConstraintFact(
            fact_id=f"pressure.alert_batch::{route_fact.fact_id}",
            fact_type=self.OUTPUT_TYPE,
            payload={"alerts": alerts},
            confidence=route_fact.confidence,
            ttl_seconds=route_fact.ttl_seconds,
            provenance={
                "tile": self.TILE_ID,
                "source_fact": route_fact.fact_id,
            },
            constraints_compliance=route_fact.constraints_compliance,
        )
        work_metrics = {
            "route_fanout": float(len(alerts)),
            "dispatch_latency_ms": float(5 * len(alerts)),
            "operation_units": float(len(alerts) * 2),
        }
        return TileExecutionResult(fact, work_metrics)

    def _build_alert(self, route_fact: ConstraintFact, target: DispatchTarget, index: int) -> Dict[str, object]:
        ratio = round(target.base_ratio + (index * 0.3), 2)
        ratio = min(ratio, target.max_ratio)
        severity = self._classify_severity(ratio)
        signal_id = f"signal::{route_fact.fact_id}::{target.tile_id}::{index}"
        return {
            "signal_id": signal_id,
            "tile_id": target.tile_id,
            "severity": severity,
            "pressure_ratio": ratio,
        }

    @staticmethod
    def _classify_severity(ratio: float) -> str:
        if ratio >= 2.5:
            return "severe"
        if ratio >= 1.5:
            return "warning"
        return "info"
