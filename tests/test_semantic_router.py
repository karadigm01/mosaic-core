from runtime.constraint_substrate import ConstraintFact
from runtime.semantic_router import SemanticRouterTile


def _turn(text: str) -> ConstraintFact:
    return ConstraintFact(
        fact_id="fact-turn",
        fact_type="conversation.turn",
        payload={"text": text},
        confidence=0.95,
        ttl_seconds=60,
        provenance={"emitter_id": "user"},
        constraints_compliance=["I1", "I2", "I3", "I4"],
    )


def test_semantic_router_matches_keyword() -> None:
    tile = SemanticRouterTile()
    result = tile.execute(_turn("Tell me the weather"))
    assert result.fact.fact_type == "conversation.route_decision"
    assert result.fact.payload["route_id"] == "route.weather"
    assert result.work_metrics["input_tokens"] >= 3
    assert result.work_metrics["operation_units"] >= result.work_metrics["input_tokens"]


def test_semantic_router_fallback() -> None:
    tile = SemanticRouterTile()
    result = tile.execute(_turn("random text"))
    assert result.fact.payload["route_id"] == "route.handoff.human"
    assert result.fact.confidence == 0.6
    assert result.work_metrics["route_checks"] == len(tile._ROUTE_TABLE) + 1  # pylint: disable=protected-access


def test_semantic_router_imagination_route() -> None:
    tile = SemanticRouterTile()
    result = tile.execute(_turn("Imagine a hypothesis"))
    assert result.fact.payload["route_id"] == "route.imagination"
    assert result.fact.payload["rationale"] == "keyword:imagine"
    assert result.work_metrics["route_checks"] >= 1
