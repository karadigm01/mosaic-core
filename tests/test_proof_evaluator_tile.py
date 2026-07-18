from __future__ import annotations

from runtime.constraint_substrate import ConstraintFact
from runtime.proof_evaluator_tile import ProofEvaluatorTile


def _build_proof_fact(**overrides):
    payload = {
        "proof_id": "proof::demo",
        "hop_metrics": [{"hop": 0}],
        "pressure_state": {"ratio": 0.8},
        "result_summary": {"status": "completed"},
        "presentation_views": [],
    }
    payload.update(overrides)
    return ConstraintFact(
        fact_id="substrate.proof_record::proof::demo",
        fact_type="substrate.proof_record",
        payload=payload,
        confidence=1.0,
        ttl_seconds=900,
        provenance={"source": "test"},
        constraints_compliance=["I1", "I2", "I3", "I4"],
    )


def test_proof_evaluator_rewards_low_pressure() -> None:
    tile = ProofEvaluatorTile()
    fact = _build_proof_fact()

    result = tile.execute(fact)

    assert result.fact.payload["score"] >= 0.75
    assert result.fact.payload["tier"] == "high"
    assert result.fact.payload["metrics"]["hop_count"] == 1.0


def test_proof_evaluator_penalizes_pressure_and_alerts() -> None:
    tile = ProofEvaluatorTile()
    fact = _build_proof_fact(
        hop_metrics=[{"hop": 0}, {"hop": 1}, {"hop": 2}],
        pressure_state={"ratio": 3.5},
        presentation_views=[
            {"type": "pressure_alert"},
            {"type": "pressure_alert"},
            {"type": "other"},
        ],
    )

    result = tile.execute(fact)

    assert result.fact.payload["tier"] == "low"
    assert result.fact.payload["score"] < 0.5
    assert "pressure_penalty" in result.fact.payload["penalties"]


def test_proof_evaluator_deterministic_outputs() -> None:
    tile = ProofEvaluatorTile()
    fact = _build_proof_fact()

    first = tile.execute(fact)
    second = tile.execute(fact)

    assert first.fact.payload == second.fact.payload
    assert first.work_metrics == second.work_metrics
