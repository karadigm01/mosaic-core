from runtime.constraint_substrate import ConstraintSubstrate, ConstraintFact
from runtime.ledger_writer import LedgerWriter
from runtime.resolver import Goal, Resolver
from runtime.tile_registry import TileContract, TileRegistry


def _fact(text: str) -> ConstraintFact:
    return ConstraintFact(
        fact_id="fact-1",
        fact_type="conversation.turn",
        payload={"text": text},
        confidence=0.95,
        ttl_seconds=60,
        provenance={"emitter_id": "user"},
        constraints_compliance=["I1", "I2", "I3", "I4"],
    )


def test_ledger_writer_exports_entries() -> None:
    substrate = ConstraintSubstrate()
    registry = TileRegistry()
    registry.register(
        TileContract(
            tile_id="tile.lang.semantic_router",
            capabilities=["conversation.route_decision"],
            resource_budget={"cpu_percent": 1},
            input_types=["conversation.turn"],
            output_types=["conversation.route_decision"],
        )
    )
    substrate.upsert_fact(_fact("What's the weather like?"))
    goal = Goal(
        goal_id="goal-writer",
        desired_output="conversation.route_decision",
        input_fact_ids=["fact-1"],
        constraints=["I1", "I2", "I3", "I4"],
    )

    resolver = Resolver(substrate, registry)
    proof = resolver.resolve(goal)

    writer = LedgerWriter(substrate)
    entries = writer.export_entries([proof.proof_id])

    assert entries[0]["proof_id"] == proof.proof_id
    assert entries[0]["pressure_state"]["status"] == "pressure_detected"
    assert entries[0]["pressure_alerts"][0]["severity"] in {"warning", "severe"}
    assert entries[0]["presentation_alerts"], "presentation alerts should propagate"
    assert entries[0]["alert_panel_views"], "alert panel view should be exported"
    assert entries[0]["chain_quality_view"], "chain quality view should be exported"
    assert entries[0]["chain_quality_fact"]["fact_type"] == "meta.chain_quality"
    assert entries[0]["pressure_history_view"], "pressure history view should be exported"
    assert entries[0]["pressure_history_fact"]["fact_type"] == "meta.pressure_history"
    assert entries[0]["signals"][0]["signal_id"].startswith("pressure::")

    report = writer.export_pressure_report()
    assert report["summary"]["pressure_detected"] >= 1
