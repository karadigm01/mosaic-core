"""Deterministic semantic router tile."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

from runtime.constraint_substrate import ConstraintFact


@dataclass(frozen=True)
class RouteDecision:
    route_id: str
    confidence: float
    rationale: str


@dataclass(frozen=True)
class TileExecutionResult:
    fact: ConstraintFact
    work_metrics: Dict[str, float]


class SemanticRouterTile:
    """Deterministic routing tile honoring constraint metadata."""

    TILE_ID = "tile.lang.semantic_router"
    OUTPUT_TYPE = "conversation.route_decision"
    INPUT_TYPES = ["conversation.input", "conversation.turn", "cognition.sentiment_result"]

    _ROUTE_TABLE: Dict[str, RouteDecision] = {
        "weather": RouteDecision("route.weather", 0.92, "keyword:weather"),
        "news": RouteDecision("route.news", 0.9, "keyword:news"),
        "help": RouteDecision("route.support", 0.88, "keyword:help"),
        "imagine": RouteDecision("route.imagination", 0.94, "keyword:imagine"),
        "hypothesis": RouteDecision("route.imagination", 0.93, "keyword:hypothesis"),
        "story": RouteDecision("route.imagination", 0.9, "keyword:story"),
    }

    def execute(self, fact: ConstraintFact) -> TileExecutionResult:
        text = self._extract_text(fact)
        normalized = text.lower()
        token_count = self._token_count(text)
        decision, route_checks = self._match_route(normalized)
        result_fact = ConstraintFact(
            fact_id=f"decision::{fact.fact_id}",
            fact_type=self.OUTPUT_TYPE,
            payload={"route_id": decision.route_id, "rationale": decision.rationale},
            confidence=decision.confidence,
            ttl_seconds=fact.ttl_seconds,
            provenance={"tile": self.TILE_ID, "source_fact": fact.fact_id},
            constraints_compliance=fact.constraints_compliance,
        )
        work_metrics = {
            "input_tokens": float(token_count),
            "route_checks": float(route_checks),
            "operation_units": float(token_count + route_checks),
        }
        return TileExecutionResult(result_fact, work_metrics)

    @staticmethod
    def _extract_text(fact: ConstraintFact) -> str:
        if fact.fact_type == "cognition.sentiment_result":
            return str(fact.payload.get("text", ""))
        return str(fact.payload.get("text", ""))

    def _match_route(self, text: str) -> Tuple[RouteDecision, int]:
        for idx, (keyword, decision) in enumerate(self._ROUTE_TABLE.items(), start=1):
            if keyword in text:
                return decision, idx
        return RouteDecision("route.handoff.human", 0.6, "fallback"), len(self._ROUTE_TABLE) + 1

    @staticmethod
    def _token_count(text: str) -> int:
        if not text:
            return 0
        return len([token for token in text.split() if token])
