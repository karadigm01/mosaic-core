"""Meta tile that scores proof records for downstream governance."""
from __future__ import annotations

from typing import Dict, List, Tuple

from runtime.constraint_substrate import ConstraintFact
from runtime.semantic_router import TileExecutionResult


class ProofEvaluatorTile:
    """Calculates deterministic chain quality metrics for proofs."""

    TILE_ID = "tile.meta.proof_evaluator"
    INPUT_TYPES = ["substrate.proof_record"]
    OUTPUT_TYPE = "meta.chain_quality"

    def execute(self, proof_fact: ConstraintFact) -> TileExecutionResult:
        metrics = self._collect_metrics(proof_fact)
        score, penalties = self._score(metrics)
        tier = self._tier(score)
        quality_fact = ConstraintFact(
            fact_id=f"meta.chain_quality::{metrics['proof_id']}",
            fact_type=self.OUTPUT_TYPE,
            payload={
                "proof_id": metrics["proof_id"],
                "score": score,
                "tier": tier,
                "metrics": metrics,
                "penalties": penalties,
            },
            confidence=0.9,
            ttl_seconds=metrics["ttl_seconds"],
            provenance={
                "tile": self.TILE_ID,
                "source_fact": proof_fact.fact_id,
            },
            constraints_compliance=proof_fact.constraints_compliance,
        )
        work_metrics = {
            "hop_count": metrics["hop_count"],
            "alert_count": metrics["alert_count"],
            "pressure_ratio": metrics["pressure_ratio"],
        }
        return TileExecutionResult(quality_fact, work_metrics)

    def _collect_metrics(self, proof_fact: ConstraintFact) -> Dict[str, float]:
        payload = proof_fact.payload
        hop_metrics = payload.get("hop_metrics") or []
        hop_count = float(len(hop_metrics))
        pressure_state = payload.get("pressure_state") or {}
        pressure_ratio = float(pressure_state.get("ratio") or 0.0)
        status = str(payload.get("result_summary", {}).get("status", "unknown"))
        presentation_views = payload.get("presentation_views") or []
        alert_count = float(
            sum(1 for view in presentation_views if isinstance(view, dict) and view.get("type") == "pressure_alert")
        )
        proof_id = str(payload.get("proof_id", proof_fact.fact_id))
        ttl_seconds = proof_fact.ttl_seconds or 600
        return {
            "proof_id": proof_id,
            "hop_count": hop_count,
            "pressure_ratio": pressure_ratio,
            "alert_count": alert_count,
            "status": status,
            "ttl_seconds": ttl_seconds,
        }

    @staticmethod
    def _score(metrics: Dict[str, float]) -> Tuple[float, Dict[str, float]]:
        penalties: Dict[str, float] = {}
        score = 1.0

        hop_penalty = min(0.4, metrics["hop_count"] * 0.05)
        if hop_penalty:
            penalties["hop_penalty"] = round(hop_penalty, 4)
            score -= hop_penalty

        pressure_penalty = 0.0
        if metrics["pressure_ratio"] > 1.0:
            pressure_penalty = min(0.5, (metrics["pressure_ratio"] - 1.0) * 0.2)
            penalties["pressure_penalty"] = round(pressure_penalty, 4)
            score -= pressure_penalty

        alert_penalty = min(0.3, metrics["alert_count"] * 0.05)
        if alert_penalty:
            penalties["alert_penalty"] = round(alert_penalty, 4)
            score -= alert_penalty

        if metrics["status"] != "completed":
            status_penalty = 0.2
            penalties["status_penalty"] = status_penalty
            score -= status_penalty

        score = round(max(score, 0.0), 4)
        return score, penalties

    @staticmethod
    def _tier(score: float) -> str:
        if score >= 0.75:
            return "high"
        if score >= 0.5:
            return "medium"
        return "low"
