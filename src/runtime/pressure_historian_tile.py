"""Meta tile that summarizes pressure signal history."""
from __future__ import annotations

from typing import Dict, List

from runtime.constraint_substrate import ConstraintFact
from runtime.semantic_router import TileExecutionResult


class PressureHistorianTile:
    """Aggregates deterministic pressure signals into governance facts."""

    TILE_ID = "tile.meta.pressure_historian"
    INPUT_TYPES = ["pressure.signal_collection"]
    OUTPUT_TYPE = "meta.pressure_history"

    def execute(self, collection_fact: ConstraintFact) -> TileExecutionResult:
        signals: List[Dict[str, object]] = list(collection_fact.payload.get("signals", []))
        metrics = self._collect_metrics(signals)
        trend = self._classify_trend(metrics)
        fact = ConstraintFact(
            fact_id=self._build_fact_id(collection_fact),
            fact_type=self.OUTPUT_TYPE,
            payload={
                "proof_id": collection_fact.payload.get("proof_id"),
                "trend": trend,
                "signal_count": metrics["signal_count"],
                "max_ratio": metrics["max_ratio"],
                "mean_ratio": metrics["mean_ratio"],
                "tile_occurrences": metrics["tile_occurrences"],
                "severity_counts": metrics["severity_counts"],
            },
            confidence=collection_fact.confidence,
            ttl_seconds=collection_fact.ttl_seconds,
            provenance={
                "tile": self.TILE_ID,
                "source_fact": collection_fact.fact_id,
            },
            constraints_compliance=collection_fact.constraints_compliance,
        )
        work_metrics = {
            "signal_count": float(metrics["signal_count"]),
            "tiles_affected": float(len(metrics["tile_occurrences"])),
            "max_ratio": metrics["max_ratio"],
        }
        return TileExecutionResult(fact, work_metrics)

    @staticmethod
    def _build_fact_id(collection_fact: ConstraintFact) -> str:
        proof_id = collection_fact.payload.get("proof_id") or collection_fact.fact_id
        return f"meta.pressure_history::{proof_id}"

    @staticmethod
    def _collect_metrics(signals: List[Dict[str, object]]) -> Dict[str, object]:
        tile_occurrences: Dict[str, int] = {}
        severity_counts = {"info": 0, "warning": 0, "severe": 0}
        ratios: List[float] = []
        for signal in signals:
            tile_id = str(signal.get("tile_id", "unknown"))
            tile_occurrences[tile_id] = tile_occurrences.get(tile_id, 0) + 1
            severity = str(signal.get("severity", "info"))
            if severity in severity_counts:
                severity_counts[severity] += 1
            ratio = float(signal.get("pressure_ratio", 0.0))
            ratios.append(ratio)
        signal_count = len(signals)
        max_ratio = max(ratios) if ratios else 0.0
        mean_ratio = sum(ratios) / signal_count if signal_count else 0.0
        return {
            "signal_count": signal_count,
            "max_ratio": round(max_ratio, 4),
            "mean_ratio": round(mean_ratio, 4),
            "tile_occurrences": tile_occurrences,
            "severity_counts": severity_counts,
        }

    @staticmethod
    def _classify_trend(metrics: Dict[str, object]) -> str:
        if metrics["signal_count"] == 0:
            return "stable"
        max_ratio = float(metrics["max_ratio"])
        mean_ratio = float(metrics["mean_ratio"])
        severity_counts = metrics["severity_counts"]
        if max_ratio >= 3.0 or severity_counts.get("severe", 0) > 0:
            return "critical"
        if mean_ratio >= 1.5 or severity_counts.get("warning", 0) >= 2:
            return "elevating"
        return "stable"
