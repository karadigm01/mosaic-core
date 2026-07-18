from __future__ import annotations

from runtime.constraint_substrate import ConstraintFact
from runtime.route_dispatch_tile import RouteDispatchTile


def _build_route_fact(route_id: str) -> ConstraintFact:
    return ConstraintFact(
        fact_id="fact.route::demo",
        fact_type="conversation.route_decision",
        payload={"route_id": route_id},
        confidence=0.9,
        ttl_seconds=120,
        provenance={"tile": "tile.lang.semantic_router"},
        constraints_compliance=["I1", "I2", "I3", "I4"],
    )


def test_route_dispatch_tile_emits_alert_batch() -> None:
    route_fact = _build_route_fact("route.support")
    tile = RouteDispatchTile()

    result = tile.execute(route_fact)

    assert result.fact.fact_type == RouteDispatchTile.OUTPUT_TYPE
    assert result.fact.payload["alerts"], "alerts should be populated"
    alert = result.fact.payload["alerts"][0]
    assert alert["signal_id"].startswith("signal::fact.route::demo")
    assert alert["tile_id"] == "tile.support.agent"
    assert result.work_metrics["route_fanout"] == len(result.fact.payload["alerts"]) 


def test_route_dispatch_tile_fallback_route() -> None:
    route_fact = _build_route_fact("route.unknown")
    tile = RouteDispatchTile()

    result = tile.execute(route_fact)

    assert result.fact.payload["alerts"][0]["tile_id"] == "tile.support.triage"
    assert result.work_metrics["route_fanout"] == len(result.fact.payload["alerts"]) 


def test_route_dispatch_tile_imagination_route() -> None:
    route_fact = _build_route_fact("route.imagination")
    tile = RouteDispatchTile()

    result = tile.execute(route_fact)

    alerts = result.fact.payload["alerts"]
    assert alerts[0]["tile_id"] == "tile.lang.guided_hallucinator"
    assert result.work_metrics["route_fanout"] == len(alerts)
