from runtime.constraint_substrate import ConstraintSubstrate, ConstraintFact, PressureSignal, ProofRecord, TileInvocation
from runtime.resolver import Goal, Resolver
from runtime.tile_registry import TileContract, TileRegistry


def test_fact_round_trip() -> None:
    substrate = ConstraintSubstrate()
    fact = ConstraintFact(
        fact_id="fact-1",
        fact_type="conversation.turn",
        payload={"text": "hi"},
        confidence=0.9,
        ttl_seconds=60,
        provenance={"emitter_id": "test"},
        constraints_compliance=["I1", "I3"],
    )
    substrate.upsert_fact(fact)
    stored = substrate.get_fact("fact-1")
    assert stored is not None
    assert stored.payload["text"] == "hi"


def test_proof_round_trip() -> None:
    substrate = ConstraintSubstrate()
    proof = ProofRecord(
        proof_id="proof-1",
        goal={"type": "conversation.route"},
        constraint_context={"invariants": ["I1", "I4"]},
        tile_sequence=[TileInvocation(tile_id="tile.lang.semantic_router", inputs=[], outputs=[])],
        capability_bindings=[{"tile_id": "tile.lang.semantic_router", "capability_id": "cap.edge.ultrabook"}],
        resource_usage={"cpu_percent": 10},
        result_summary={"status": "ok"},
        presentation_views=[],
        audit_hash="hash://sha256/demo",
    )
    substrate.record_proof(proof)
    stored = substrate.get_proof("proof-1")
    assert stored is not None
    assert stored.audit_hash == "hash://sha256/demo"


def test_goal_definition() -> None:
    goal = Goal(
        goal_id="goal-1",
        desired_output="conversation.route_decision",
        input_fact_ids=["fact-1"],
        constraints=["I1", "I2", "I3", "I4"],
        capability_preferences=["cap.edge.ultrabook"],
    )
    assert goal.desired_output == "conversation.route_decision"
    assert goal.capability_preferences == ["cap.edge.ultrabook"]


def test_resolver_emits_proof_record() -> None:
    substrate = ConstraintSubstrate()
    registry = TileRegistry()
    registry.register(
        TileContract(
            tile_id="tile.lang.semantic_router",
            capabilities=["conversation.route_decision", "cap.edge.ultrabook"],
            resource_budget={"cpu_percent": 2},
            input_types=["conversation.turn"],
            output_types=["conversation.route_decision"],
        )
    )
    fact = ConstraintFact(
        fact_id="fact-1",
        fact_type="conversation.turn",
        payload={"text": "What's the weather like?"},
        confidence=0.95,
        ttl_seconds=120,
        provenance={"emitter_id": "user"},
        constraints_compliance=["I1", "I2", "I3", "I4"],
    )
    substrate.upsert_fact(fact)
    goal = Goal(
        goal_id="goal-route",
        desired_output="conversation.route_decision",
        input_fact_ids=["fact-1"],
        constraints=["I1", "I2", "I3", "I4"],
        capability_preferences=["cap.edge.ultrabook"],
    )

    resolver = Resolver(substrate, registry)
    proof = resolver.resolve(goal)

    assert proof.goal["desired_output"] == "conversation.route_decision"
    assert proof.tile_sequence[0].tile_id == "tile.lang.semantic_router"
    assert proof.tile_sequence[0].inputs == ["fact-1"]
    assert proof.capability_bindings[0]["capability_id"] == "cap.edge.ultrabook"
    hop_metrics = proof.resource_usage["hop_metrics"][0]
    work_metrics = hop_metrics["work_metrics"]
    assert work_metrics["input_tokens"] >= 1
    assert work_metrics["route_checks"] >= 1
    assert work_metrics["operation_units"] >= work_metrics["input_tokens"]
    pressure_state = proof.resource_usage["pressure_state"]
    assert pressure_state["status"] == "pressure_detected"
    assert pressure_state["ratio"] > 1.0
    assert pressure_state["signal_id"].startswith("pressure::")
    recorded_signal = substrate.get_pressure_signal(pressure_state["signal_id"])
    assert recorded_signal is not None
    assert recorded_signal.proof_id == proof.proof_id
    assert recorded_signal.goal_id == goal.goal_id
    alerts = substrate.list_alerts()
    assert len(alerts) == 1
    assert alerts[0]["signal_id"] == recorded_signal.signal_id
    assert alerts[0]["severity"] in {"warning", "severe"}
    decision_fact_id = proof.tile_sequence[0].outputs[0]
    decision_fact = substrate.get_fact(decision_fact_id)
    assert decision_fact is not None
    assert decision_fact.payload["route_id"] == "route.weather"
    assert proof.result_summary["outputs"][0]["route_id"] == "route.weather"
    assert proof.presentation_views[0]["audit_hash"] == proof.audit_hash
    assert proof.presentation_views[0]["proof_id"] == proof.proof_id
    alert_panel_views = [view for view in proof.presentation_views if view.get("type") == "alert_panel"]
    if alert_panel_views:
        assert alert_panel_views[0]["proof_id"] == proof.proof_id
    assert proof.ledger_metadata["pressure_signal"]["signal_id"] == pressure_state["signal_id"]
    assert proof.ledger_metadata["pressure_state"]["status"] == "pressure_detected"
    ledger_entry = substrate.build_ledger_entry(proof.proof_id)
    assert ledger_entry["proof_id"] == proof.proof_id
    assert ledger_entry["pressure_alerts"][0]["severity"] in {"warning", "severe"}
    assert ledger_entry["presentation_alerts"][0]["signal_id"] == recorded_signal.signal_id
    if ledger_entry["alert_panel_views"]:
        assert ledger_entry["alert_panel_views"][0]["type"] == "alert_panel"
    assert ledger_entry["chain_quality_view"]["type"] == "chain_quality"
    assert ledger_entry["chain_quality_fact"]["fact_type"] == "meta.chain_quality"
    assert ledger_entry["pressure_history_view"]["type"] == "pressure_history"
    assert ledger_entry["pressure_history_fact"]["fact_type"] == "meta.pressure_history"
    assert substrate.get_proof(proof.proof_id) is proof
    chain_views = [view for view in proof.presentation_views if view.get("type") == "chain_quality"]
    assert chain_views, "proof should include chain quality view"
    chain_fact = substrate.get_fact(f"meta.chain_quality::{proof.proof_id}")
    assert chain_fact is not None
    assert chain_fact.payload["proof_id"] == proof.proof_id
    history_views = [view for view in proof.presentation_views if view.get("type") == "pressure_history"]
    assert history_views, "proof should include pressure history view"
    history_fact = substrate.get_fact(f"meta.pressure_history::{proof.proof_id}")
    assert history_fact is not None
    assert history_fact.payload["proof_id"] == proof.proof_id


def test_pressure_summary_and_alerts() -> None:
    substrate = ConstraintSubstrate()
    signal = PressureSignal(
        signal_id="pressure::proof::tile",
        proof_id="proof::demo",
        goal_id="goal-demo",
        tile_id="tile.lang.semantic_router",
        metric="operation_units",
        observed_value=4.0,
        contract_budget=1.0,
        pressure_ratio=4.0,
    )
    substrate.record_pressure_signal(signal)

    summary = substrate.pressure_summary()
    assert summary["pressure_detected"] == 1
    assert summary["max_ratio"] == 4.0
    assert summary["tiles"]["tile.lang.semantic_router"] == 1

    alerts = substrate.pressure_alerts(ratio_threshold=3.0)
    assert len(alerts) == 1
    assert alerts[0].signal_id == signal.signal_id


def test_pressure_report_export() -> None:
    substrate = ConstraintSubstrate()
    signal = PressureSignal(
        signal_id="pressure::export",
        proof_id="proof::export",
        goal_id="goal-export",
        tile_id="tile.lang.semantic_router",
        metric="operation_units",
        observed_value=5.0,
        contract_budget=1.0,
        pressure_ratio=5.0,
    )
    substrate.record_pressure_signal(signal)
    substrate.record_alert(signal, "severe")

    report = substrate.export_pressure_report()
    assert report["summary"]["pressure_detected"] == 1
    assert report["signals"][0]["signal_id"] == signal.signal_id
    assert report["alerts"][0]["severity"] == "severe"


def test_resolver_records_failure_when_fact_missing() -> None:
    substrate = ConstraintSubstrate()
    registry = TileRegistry()
    registry.register(
        TileContract(
            tile_id="tile.lang.semantic_router",
            capabilities=["conversation.route_decision"],
            resource_budget={"cpu_percent": 10},
            input_types=["conversation.turn"],
            output_types=["conversation.route_decision"],
        )
    )
    goal = Goal(
        goal_id="goal-missing-fact",
        desired_output="conversation.route_decision",
        input_fact_ids=["fact-missing"],
        constraints=["I1"],
    )

    resolver = Resolver(substrate, registry)
    proof = resolver.resolve(goal)

    assert proof.result_summary["status"] == "rejected"
    assert "fact fact-missing" in proof.result_summary["reason"]
    assert proof.tile_sequence == []
    chain_quality = proof.resource_usage.get("chain_quality")
    assert chain_quality is not None
    assert chain_quality["proof_id"] == proof.proof_id
    assert substrate.get_proof(proof.proof_id) is proof


def test_resolver_records_failure_when_capability_missing() -> None:
    substrate = ConstraintSubstrate()
    registry = TileRegistry()
    fact = ConstraintFact(
        fact_id="fact-2",
        fact_type="conversation.turn",
        payload={"text": "Hi"},
        confidence=0.9,
        ttl_seconds=60,
        provenance={"emitter_id": "user"},
        constraints_compliance=["I1"],
    )
    substrate.upsert_fact(fact)
    goal = Goal(
        goal_id="goal-no-tile",
        desired_output="conversation.route_decision",
        input_fact_ids=["fact-2"],
        constraints=["I1"],
    )

    resolver = Resolver(substrate, registry)
    proof = resolver.resolve(goal)

    assert proof.result_summary["status"] == "rejected"
    assert "no tile registered" in proof.result_summary["reason"]
    assert proof.capability_bindings == []
    chain_quality = proof.resource_usage.get("chain_quality")
    assert chain_quality is not None
    assert chain_quality["proof_id"] == proof.proof_id
    assert substrate.get_proof(proof.proof_id) is proof
