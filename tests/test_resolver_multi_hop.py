from __future__ import annotations

import pytest

from runtime.constraint_substrate import ConstraintFact, ConstraintSubstrate
from runtime.guided_hallucinator_tile import GuidedHallucinatorTile
from runtime.resolver import Goal, Resolver
from runtime.route_dispatch_tile import RouteDispatchTile
from runtime.semantic_router import SemanticRouterTile, TileExecutionResult
from runtime.pressure_summary_tile import PressureSummaryTile
from runtime.sentiment_tile import SentimentTile
from runtime.tile_registry import TileContract, TileRegistry
from runtime.tinyllama_health import TinyLlamaHealthSnapshot


def _build_substrate(
    *, include_goal_input: bool = True, include_user_text: bool = False, include_conversation_turn: bool = False
) -> ConstraintSubstrate:
    substrate = ConstraintSubstrate()
    if include_goal_input:
        substrate.upsert_fact(
            ConstraintFact(
                fact_id="fact.goal_input",
                fact_type="conversation.input",
                payload={"text": "Need weather help"},
                confidence=1.0,
                ttl_seconds=300,
                provenance={"source": "test"},
                constraints_compliance=["I1", "I2", "I3", "I4"],
            )
        )
    if include_user_text:
        substrate.upsert_fact(
            ConstraintFact(
                fact_id="fact.user_text",
                fact_type="user.text_input",
                payload={"text": "I hate waiting"},
                confidence=1.0,
                ttl_seconds=300,
                provenance={"source": "test"},
                constraints_compliance=["I1", "I2", "I3", "I4"],
            )
        )
    if include_conversation_turn:
        substrate.upsert_fact(
            ConstraintFact(
                fact_id="fact.conversation.turn",
                fact_type="conversation.turn",
                payload={"text": "Imagine a hypothesis about glass cities."},
                confidence=0.95,
                ttl_seconds=300,
                provenance={"source": "test"},
                constraints_compliance=["I1", "I2", "I3", "I4"],
            )
        )
    return substrate


def _build_registry() -> TileRegistry:
    registry = TileRegistry()
    registry.register(
        TileContract(
            tile_id=SentimentTile.TILE_ID,
            capabilities=["text.sentiment"],
            resource_budget={"cpu_percent": 15},
            input_types=["user.text_input"],
            output_types=[SentimentTile.OUTPUT_TYPE],
        )
    )
    registry.register(
        TileContract(
            tile_id=SemanticRouterTile.TILE_ID,
            capabilities=["conversation.route"],
            resource_budget={"cpu_percent": 20},
            input_types=["conversation.input", "cognition.sentiment_result"],
            output_types=[SemanticRouterTile.OUTPUT_TYPE],
        )
    )
    registry.register(
        TileContract(
            tile_id=RouteDispatchTile.TILE_ID,
            capabilities=["route.dispatch"],
            resource_budget={"cpu_percent": 25},
            input_types=RouteDispatchTile.INPUT_TYPES,
            output_types=[RouteDispatchTile.OUTPUT_TYPE],
        )
    )
    registry.register(
        TileContract(
            tile_id=PressureSummaryTile.TILE_ID,
            capabilities=["pressure.summary"],
            resource_budget={"cpu_percent": 15},
            input_types=[RouteDispatchTile.OUTPUT_TYPE],
            output_types=[PressureSummaryTile.OUTPUT_TYPE],
        )
    )
    registry.register(
        TileContract(
            tile_id=GuidedHallucinatorTile.TILE_ID,
            capabilities=["conversation.imagination", "conversation.hypothesis"],
            resource_budget={"cpu_percent": 25},
            input_types=GuidedHallucinatorTile.INPUT_TYPES,
            output_types=[GuidedHallucinatorTile.OUTPUT_TYPE],
        )
    )
    return registry


def test_resolver_executes_multi_tile_plan() -> None:
    substrate = _build_substrate()
    registry = _build_registry()
    resolver = Resolver(substrate, registry)

    goal = Goal(
        goal_id="goal.multi",
        desired_output="route.dispatch",
        input_fact_ids=["fact.goal_input"],
        constraints=["I1", "I2", "I3", "I4"],
        capability_plan=["conversation.route", "route.dispatch"],
    )

    proof = resolver.resolve(goal)

    assert len(proof.tile_sequence) == 2
    assert proof.result_summary["status"] == "completed"
    assert proof.capability_bindings[0]["tile_id"] == SemanticRouterTile.TILE_ID
    assert proof.capability_bindings[1]["tile_id"] == RouteDispatchTile.TILE_ID
    assert proof.resource_usage["hop_metrics"], "hop metrics should list per hop data"


def test_resolver_handles_partial_chain_failure() -> None:
    substrate = _build_substrate()
    registry = _build_registry()
    resolver = Resolver(substrate, registry)

    goal = Goal(
        goal_id="goal.invalid",
        desired_output="route.dispatch",
        input_fact_ids=["missing.fact"],
        constraints=["I1", "I2", "I3", "I4"],
        capability_plan=["conversation.route", "route.dispatch"],
    )

    proof = resolver.resolve(goal)

    assert proof.result_summary["status"] == "rejected"
    assert proof.result_summary["error_code"] == "missing_fact"
    assert proof.tile_sequence == []


def test_resolver_reports_failure_when_downstream_tile_missing_implementation() -> None:
    substrate = _build_substrate()
    registry = _build_registry()
    registry.register(
        TileContract(
            tile_id="tile.reasoning.incomplete",
            capabilities=["route.dispatch.incomplete"],
            resource_budget={"cpu_percent": 10},
            input_types=[SemanticRouterTile.OUTPUT_TYPE],
            output_types=["route.dispatch.incomplete"],
        )
    )
    resolver = Resolver(substrate, registry)

    goal = Goal(
        goal_id="goal.partial_failure",
        desired_output="route.dispatch",
        input_fact_ids=["fact.goal_input"],
        constraints=["I1", "I2", "I3", "I4"],
        capability_plan=["conversation.route", "route.dispatch.incomplete"],
    )

    proof = resolver.resolve(goal)

    assert proof.result_summary["status"] == "rejected"
    assert proof.result_summary["error_code"] == "resolver_error"
    assert proof.tile_sequence == []


def test_resolver_infers_plan_without_manual_capability_chain() -> None:
    substrate = _build_substrate()
    registry = _build_registry()
    resolver = Resolver(substrate, registry)

    goal = Goal(
        goal_id="goal.auto",
        desired_output="route.dispatch",
        input_fact_ids=["fact.goal_input"],
        constraints=["I1", "I2", "I3", "I4"],
    )

    proof = resolver.resolve(goal)

    assert [invocation.tile_id for invocation in proof.tile_sequence] == [
        SemanticRouterTile.TILE_ID,
        RouteDispatchTile.TILE_ID,
    ]
    assert proof.result_summary["status"] == "completed"


def test_resolver_falls_back_to_capability_lookup_when_inference_missing() -> None:
    substrate = _build_substrate()
    registry = TileRegistry()
    registry.register(
        TileContract(
            tile_id=RouteDispatchTile.TILE_ID,
            capabilities=["route.dispatch"],
            resource_budget={"cpu_percent": 10},
            input_types=RouteDispatchTile.INPUT_TYPES,
            output_types=[RouteDispatchTile.OUTPUT_TYPE],
        )
    )
    resolver = Resolver(substrate, registry)

    goal = Goal(
        goal_id="goal.fallback",
        desired_output="route.dispatch",
        input_fact_ids=["fact.goal_input"],
        constraints=["I1", "I2", "I3", "I4"],
    )

    proof = resolver.resolve(goal)

    assert [binding["tile_id"] for binding in proof.capability_bindings] == [RouteDispatchTile.TILE_ID]
    assert proof.result_summary["status"] == "completed"


def test_resolver_reports_capability_not_found_when_registry_missing_tile() -> None:
    substrate = _build_substrate()
    registry = TileRegistry()
    resolver = Resolver(substrate, registry)

    goal = Goal(
        goal_id="goal.missing_tile",
        desired_output="route.dispatch",
        input_fact_ids=["fact.goal_input"],
        constraints=["I1", "I2", "I3", "I4"],
    )

    proof = resolver.resolve(goal)

    assert proof.result_summary["status"] == "rejected"
    assert proof.result_summary["error_code"] == "capability_not_found"


def test_resolver_infers_branching_capability_path() -> None:
    substrate = _build_substrate()
    registry = _build_registry()
    resolver = Resolver(substrate, registry)

    goal = Goal(
        goal_id="goal.branch",
        desired_output="pressure.summary",
        input_fact_ids=["fact.goal_input"],
        constraints=["I1", "I2", "I3", "I4"],
    )

    proof = resolver.resolve(goal)

    assert [invocation.tile_id for invocation in proof.tile_sequence] == [
        SemanticRouterTile.TILE_ID,
        RouteDispatchTile.TILE_ID,
        PressureSummaryTile.TILE_ID,
    ]
    assert proof.result_summary["status"] == "completed"


def test_resolver_ignores_incompatible_branch_options() -> None:
    substrate = _build_substrate()
    registry = _build_registry()
    registry.register(
        TileContract(
            tile_id="tile.reasoning.unreachable_pressure",
            capabilities=["pressure.summary"],
            resource_budget={"cpu_percent": 10},
            input_types=["conversation.input.unused"],
            output_types=["pressure.summary"],
        )
    )
    resolver = Resolver(substrate, registry)

    goal = Goal(
        goal_id="goal.branch_incompatible",
        desired_output="pressure.summary",
        input_fact_ids=["fact.goal_input"],
        constraints=["I1", "I2", "I3", "I4"],
    )

    proof = resolver.resolve(goal)

    assert [invocation.tile_id for invocation in proof.tile_sequence] == [
        SemanticRouterTile.TILE_ID,
        RouteDispatchTile.TILE_ID,
        PressureSummaryTile.TILE_ID,
    ]
    assert proof.result_summary["status"] == "completed"


def test_resolver_executes_sentiment_to_support_chain() -> None:
    substrate = _build_substrate(include_goal_input=False, include_user_text=True)
    registry = _build_registry()
    resolver = Resolver(substrate, registry)

    goal = Goal(
        goal_id="goal.sentiment_support",
        desired_output="route.dispatch",
        input_fact_ids=["fact.user_text"],
        constraints=["I1", "I2", "I3", "I4"],
    )

    proof = resolver.resolve(goal)

    assert [invocation.tile_id for invocation in proof.tile_sequence] == [
        SentimentTile.TILE_ID,
        SemanticRouterTile.TILE_ID,
        RouteDispatchTile.TILE_ID,
    ]
    assert proof.result_summary["status"] == "completed"


def test_resolver_emits_alert_panel_view_on_pressure() -> None:
    substrate = _build_substrate()
    registry = TileRegistry()
    registry.register(
        TileContract(
            tile_id=SemanticRouterTile.TILE_ID,
            capabilities=["conversation.route"],
            resource_budget={"cpu_percent": 1},
            input_types=["conversation.input"],
            output_types=[SemanticRouterTile.OUTPUT_TYPE],
        )
    )
    registry.register(
        TileContract(
            tile_id=RouteDispatchTile.TILE_ID,
            capabilities=["route.dispatch"],
            resource_budget={"cpu_percent": 1},
            input_types=RouteDispatchTile.INPUT_TYPES,
            output_types=[RouteDispatchTile.OUTPUT_TYPE],
        )
    )
    resolver = Resolver(substrate, registry)

    goal = Goal(
        goal_id="goal.alert_panel",
        desired_output="route.dispatch",
        input_fact_ids=["fact.goal_input"],
        constraints=["I1", "I2", "I3", "I4"],
    )

    proof = resolver.resolve(goal)

    alert_panel_views = [view for view in proof.presentation_views if view.get("type") == "alert_panel"]
    assert alert_panel_views, "alert panel view should be emitted when pressure occurs"
    history_views = [view for view in proof.presentation_views if view.get("type") == "pressure_history"]
    assert history_views, "pressure history view should be emitted when pressure occurs"
    pressure_history = proof.resource_usage.get("pressure_history")
    assert pressure_history is not None
    assert pressure_history["signal_count"] >= 1


def test_resolver_emits_chain_quality_view() -> None:
    substrate = _build_substrate()
    registry = _build_registry()
    resolver = Resolver(substrate, registry)

    goal = Goal(
        goal_id="goal.chain_quality",
        desired_output="pressure.summary",
        input_fact_ids=["fact.goal_input"],
        constraints=["I1", "I2", "I3", "I4"],
    )

    proof = resolver.resolve(goal)

    chain_views = [view for view in proof.presentation_views if view.get("type") == "chain_quality"]
    assert chain_views, "chain quality view should be appended"
    chain_payload = proof.resource_usage["chain_quality"]
    assert chain_payload["proof_id"] == proof.proof_id
    assert 0.0 <= chain_payload["score"] <= 1.0


def test_resolver_tracks_within_budget_pressure_state() -> None:
    substrate = _build_substrate()
    registry = _build_registry()
    resolver = Resolver(substrate, registry)

    goal = Goal(
        goal_id="goal.within_budget",
        desired_output="route.dispatch",
        input_fact_ids=["fact.goal_input"],
        constraints=["I1", "I2", "I3", "I4"],
    )

    proof = resolver.resolve(goal)

    pressure_state = proof.resource_usage.get("pressure_state")
    assert pressure_state is not None
    assert pressure_state["status"] == "within_budget"
    assert 0.0 < pressure_state["ratio"] <= 1.0
    assert proof.ledger_metadata.get("pressure_signal") is None


def test_resolver_capability_preferences_are_respected() -> None:
    substrate = _build_substrate()
    registry = TileRegistry()
    registry.register(
        TileContract(
            tile_id=SemanticRouterTile.TILE_ID,
            capabilities=["conversation.route", "conversation.route.alt"],
            resource_budget={"cpu_percent": 10},
            input_types=["conversation.input"],
            output_types=[SemanticRouterTile.OUTPUT_TYPE],
        )
    )
    registry.register(
        TileContract(
            tile_id=RouteDispatchTile.TILE_ID,
            capabilities=["route.dispatch", "route.dispatch.alt"],
            resource_budget={"cpu_percent": 10},
            input_types=RouteDispatchTile.INPUT_TYPES,
            output_types=[RouteDispatchTile.OUTPUT_TYPE],
        )
    )
    resolver = Resolver(substrate, registry)

    goal = Goal(
        goal_id="goal.cap_pref",
        desired_output="route.dispatch",
        input_fact_ids=["fact.goal_input"],
        constraints=["I1", "I2", "I3", "I4"],
        capability_preferences=["conversation.route.alt", "route.dispatch.alt"],
    )

    proof = resolver.resolve(goal)

    bindings = proof.capability_bindings
    assert bindings[0]["capability_id"] == "conversation.route.alt"
    assert bindings[1]["capability_id"] == "route.dispatch.alt"


def test_resolver_attaches_pressure_signal_metadata() -> None:
    substrate = _build_substrate()
    registry = TileRegistry()
    registry.register(
        TileContract(
            tile_id=SemanticRouterTile.TILE_ID,
            capabilities=["conversation.route"],
            resource_budget={"cpu_percent": 1},
            input_types=["conversation.input"],
            output_types=[SemanticRouterTile.OUTPUT_TYPE],
        )
    )
    registry.register(
        TileContract(
            tile_id=RouteDispatchTile.TILE_ID,
            capabilities=["route.dispatch"],
            resource_budget={"cpu_percent": 1},
            input_types=RouteDispatchTile.INPUT_TYPES,
            output_types=[RouteDispatchTile.OUTPUT_TYPE],
        )
    )
    resolver = Resolver(substrate, registry)

    goal = Goal(
        goal_id="goal.pressure_metadata",
        desired_output="route.dispatch",
        input_fact_ids=["fact.goal_input"],
        constraints=["I1", "I2", "I3", "I4"],
    )

    proof = resolver.resolve(goal)

    metadata_signal = proof.ledger_metadata.get("pressure_signal")
    assert metadata_signal is not None
    assert metadata_signal["tile_id"] == RouteDispatchTile.TILE_ID
    assert metadata_signal["metric"] == "operation_units"
    assert metadata_signal["pressure_ratio"] > 1.0


def test_resolver_surfaces_hallucinator_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    substrate = _build_substrate(include_goal_input=False, include_conversation_turn=True)
    registry = _build_registry()
    resolver = Resolver(substrate, registry)

    class StubHallucinator:
        TILE_ID = GuidedHallucinatorTile.TILE_ID

        def execute(self, fact: ConstraintFact) -> TileExecutionResult:
            payload = {
                "request_uuid": "stubbed-uuid",
                "hypothesis": {"summary": "Hypothesis: glass cities thrive."},
                "self_assessment": {"confidence": 0.88},
                "outcome": "success",
                "telemetry": {
                    "slot_contention_events": 0,
                    "health_snapshot": {
                        "is_available": True,
                        "status_code": 200,
                        "latency_ms": 12,
                        "failure_reason": None,
                        "probed_at": 0.0,
                    },
                },
            }
            result_fact = ConstraintFact(
                fact_id=f"hypothesis::{fact.fact_id}",
                fact_type=GuidedHallucinatorTile.OUTPUT_TYPE,
                payload=payload,
                confidence=0.88,
                ttl_seconds=300,
                provenance={"tile": GuidedHallucinatorTile.TILE_ID},
                constraints_compliance=fact.constraints_compliance,
            )
            return TileExecutionResult(result_fact, {"operation_units": 42.0})

    monkeypatch.setitem(Resolver._TILE_IMPLEMENTATIONS, GuidedHallucinatorTile.TILE_ID, StubHallucinator)

    goal = Goal(
        goal_id="goal.snapshot",
        desired_output=GuidedHallucinatorTile.OUTPUT_TYPE,
        input_fact_ids=["fact.conversation.turn"],
        constraints=["I1", "I2", "I3", "I4"],
        capability_plan=["conversation.route", "conversation.imagination"],
    )

    proof = resolver.resolve(goal)

    hypothesis_views = [view for view in proof.presentation_views if view.get("type") == "hallucinator_hypothesis"]
    assert hypothesis_views, "hallucinator hypothesis view should be appended"
    assert hypothesis_views[0]["summary"].startswith("Hypothesis: glass cities")

    snapshot = proof.ledger_metadata.get("hallucinator_snapshot")
    assert snapshot is not None
    assert snapshot["summary"].startswith("Hypothesis: glass cities")
    assert snapshot["outcome"] == "success"
    telemetry = snapshot.get("telemetry", {})
    assert telemetry.get("health_snapshot", {}).get("is_available") is True


@pytest.mark.integration
def test_resolver_executes_guided_hallucinator_path_live(
    tinyllama_health_snapshot: TinyLlamaHealthSnapshot,
) -> None:
    if not tinyllama_health_snapshot.is_available:
        pytest.skip(
            f"TinyLLaMA server not reachable on 8088: {tinyllama_health_snapshot.failure_reason}"
        )

    substrate = _build_substrate(include_goal_input=False, include_conversation_turn=True)
    registry = _build_registry()
    resolver = Resolver(substrate, registry)

    goal = Goal(
        goal_id="goal.imagination",
        desired_output=GuidedHallucinatorTile.OUTPUT_TYPE,
        input_fact_ids=["fact.conversation.turn"],
        constraints=["I1", "I2", "I3", "I4"],
        capability_plan=["conversation.route", "conversation.imagination"],
    )

    proof = resolver.resolve(goal)

    if proof.result_summary.get("status") != "completed":
        pytest.skip(f"Guided hallucinator live call failed: {proof.result_summary}")

    assert [invocation.tile_id for invocation in proof.tile_sequence] == [
        SemanticRouterTile.TILE_ID,
        GuidedHallucinatorTile.TILE_ID,
    ]
    assert proof.result_summary["status"] == "completed"
    outputs = proof.result_summary["outputs"]
    assert outputs, "guided hallucinator should emit a hypothesis fact"
    hypothesis = outputs[0]["hypothesis"]["summary"].strip()
    assert hypothesis, "TinyLLaMA should provide hypothesis text"
    assert proof.capability_bindings[-1]["capability_id"] == "conversation.imagination"