"""Goal definitions and resolver orchestration with multi-hop execution."""
from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from runtime.constraint_substrate import (
    ConstraintFact,
    ConstraintSubstrate,
    PressureSignal,
    ProofRecord,
    TileInvocation,
)
from runtime.guided_hallucinator_tile import GuidedHallucinatorTile
from runtime.pressure_historian_tile import PressureHistorianTile
from runtime.pressure_summary_tile import PressureSummaryTile
from runtime.proof_evaluator_tile import ProofEvaluatorTile
from runtime.route_dispatch_tile import RouteDispatchTile
from runtime.semantic_router import SemanticRouterTile, TileExecutionResult
from runtime.sentiment_tile import SentimentTile
from runtime.tile_registry import TileContract, TileRegistry


@dataclass(frozen=True)
class Goal:
    """Structured intent describing the desired output and constraints."""

    goal_id: str
    desired_output: str
    input_fact_ids: List[str]
    constraints: List[str]
    capability_preferences: Optional[List[str]] = None
    capability_plan: Optional[List[str]] = None


class Resolver:
    """Deterministic resolver that can execute multi-hop capability chains."""

    _TILE_IMPLEMENTATIONS = {
        SemanticRouterTile.TILE_ID: SemanticRouterTile,
        RouteDispatchTile.TILE_ID: RouteDispatchTile,
        PressureSummaryTile.TILE_ID: PressureSummaryTile,
        SentimentTile.TILE_ID: SentimentTile,
        GuidedHallucinatorTile.TILE_ID: GuidedHallucinatorTile,
    }

    def __init__(self, substrate: ConstraintSubstrate, registry: TileRegistry) -> None:
        self._substrate = substrate
        self._registry = registry

    def resolve(self, goal: Goal) -> ProofRecord:
        self._ensure_constraints(goal)
        try:
            input_facts = self._resolve_facts(goal)
            capability_plan = self._plan_capabilities(goal, input_facts)
            proof = self._execute_plan(goal, input_facts, capability_plan)
        except Exception as exc:  # pylint: disable=broad-except
            proof = self._build_failure_proof(goal, exc)
        self._substrate.record_proof(proof)
        return proof

    def _ensure_constraints(self, goal: Goal) -> None:
        if not goal.constraints:
            raise ValueError("goal must declare constraints")

    def _resolve_facts(self, goal: Goal) -> List[ConstraintFact]:
        facts: List[ConstraintFact] = []
        for fact_id in goal.input_fact_ids:
            fact = self._substrate.get_fact(fact_id)
            if fact is None:
                raise ValueError(f"fact {fact_id} missing from substrate")
            facts.append(fact)
        if not facts:
            raise ValueError("goal requires at least one input fact")
        return facts

    def _plan_capabilities(self, goal: Goal, input_facts: List[ConstraintFact]) -> List[str]:
        if goal.capability_plan:
            return list(goal.capability_plan)

        inferred: List[str] = []
        input_types = {fact.fact_type for fact in input_facts}

        if goal.desired_output == "route.dispatch":
            if "user.text_input" in input_types:
                inferred.append("text.sentiment")
            inferred.extend(["conversation.route", "route.dispatch"])
            if self._capabilities_available(inferred):
                return inferred

        if goal.desired_output == "pressure.summary":
            inferred.extend(["conversation.route", "route.dispatch", "pressure.summary"])
            if self._capabilities_available(inferred):
                return inferred

        if goal.desired_output in {GuidedHallucinatorTile.OUTPUT_TYPE, "conversation.hypothesis"}:
            inferred.extend(["conversation.route", "conversation.imagination"])
            if self._capabilities_available(inferred):
                return inferred

        # fallback: try desired_output directly
        return [goal.desired_output]

    def _capabilities_available(self, capabilities: List[str]) -> bool:
        try:
            for capability in capabilities:
                self._registry.find_by_capability(capability)
            return True
        except Exception:
            return False

    def _execute_plan(self, goal: Goal, input_facts: List[ConstraintFact], capability_plan: List[str]) -> ProofRecord:
        tile_sequence: List[TileInvocation] = []
        capability_bindings: List[Dict[str, str]] = []
        presentation_views: List[Dict[str, object]] = []
        hop_metrics: List[Dict[str, object]] = []
        signals: List[PressureSignal] = []
        alerts: List[Dict[str, object]] = []
        last_fact = input_facts[-1]

        for capability in capability_plan:
            contract = self._registry.find_by_capability(capability)
            capability_id = self._select_capability(goal, contract)
            tile_cls = self._TILE_IMPLEMENTATIONS.get(contract.tile_id)
            if tile_cls is None:
                raise ValueError(f"no implementation registered for {contract.tile_id}")

            # pick an input fact compatible with the contract, fall back to last_fact
            candidate = self._pick_fact_for_contract(contract, [last_fact] + input_facts)
            result = self._execute_tile(tile_cls, candidate)

            self._substrate.upsert_fact(result.fact)

            invocation = TileInvocation(
                tile_id=contract.tile_id,
                inputs=[candidate.fact_id],
                outputs=[result.fact.fact_id],
            )
            tile_sequence.append(invocation)
            capability_bindings.append({"tile_id": contract.tile_id, "capability_id": capability_id})

            ratio = self._compute_pressure_ratio(result.work_metrics, contract)
            hop_metrics.append(
                {
                    "tile_id": contract.tile_id,
                    "capability_id": capability_id,
                    "work_metrics": result.work_metrics,
                    "budget": contract.resource_budget,
                    "ratio": ratio,
                }
            )

            if ratio > 1.0:
                signal = self._record_pressure(goal, contract, result, ratio)
                signals.append(signal)
                alert = self._build_alert_view(signal)
                alerts.append(alert)
                presentation_views.append(alert)
                presentation_views.append(self._build_alert_panel_view(goal, signal))

            last_fact = result.fact
                        "summary": result.fact.payload.get("hypothesis", {}).get("summary", ""),

            if contract.tile_id == GuidedHallucinatorTile.TILE_ID:
                presentation_views.append(
                    {
                        "type": "hallucinator_hypothesis",
                        "fact_id": result.fact.fact_id,
                    }
                )

        pressure_state = self._summarize_pressure(signals, hop_metrics)
        resource_usage: Dict[str, object] = {
            "hop_metrics": hop_metrics,
            "pressure_state": pressure_state,
        }

        ledger_metadata: Dict[str, object] = {}
        if pressure_state.get("signal_id"):
            ledger_metadata["pressure_signal"] = pressure_state
            ledger_metadata["pressure_state"] = pressure_state

        result_summary = self._build_result_summary(last_fact, tile_sequence)
        proof = ProofRecord(
            proof_id=self._build_proof_id(goal.goal_id, tile_sequence[-1].tile_id if tile_sequence else "failure"),
            goal=self._serialize_goal(goal),
            constraint_context={"requested_invariants": goal.constraints},
            tile_sequence=tile_sequence,
            capability_bindings=capability_bindings,
            resource_usage=resource_usage,
            result_summary=result_summary,
            presentation_views=presentation_views,
            ledger_metadata=ledger_metadata,
            audit_hash=None,
        )

        # attach chain quality + pressure history views/facts
        self._append_chain_quality(proof)
        self._append_pressure_history(proof, signals)

        # prepend route decision view for downstream consumers
        if tile_sequence:
            last_invocation = tile_sequence[-1]
            proof.presentation_views.insert(
                0,
                {
                    "type": "route_decision",
                    "fact_id": last_invocation.outputs[0],
                    "proof_id": proof.proof_id,
                },
            )

        proof.audit_hash = self._hash_proof(proof)
        # back-fill audit hash onto chain quality view for downstream tests
        for view in proof.presentation_views:
            if view.get("type") == "chain_quality":
                view["audit_hash"] = proof.audit_hash
                view["proof_id"] = proof.proof_id
            if view.get("type") == "alert_panel":
                view["proof_id"] = proof.proof_id
            if view.get("type") == "route_decision":
                view["audit_hash"] = proof.audit_hash

        return proof

    def _pick_fact_for_contract(self, contract: TileContract, facts: List[ConstraintFact]) -> ConstraintFact:
        for fact in facts:
            if fact.fact_type in contract.input_types:
                return fact
        return facts[0]

    @staticmethod
    def _compute_pressure_ratio(work_metrics: Dict[str, float], contract: TileContract) -> float:
        op_units = work_metrics.get("operation_units", 0.0)
        budget = contract.resource_budget.get("cpu_percent", 1.0) or 1.0
        return op_units / budget

    def _execute_tile(self, tile_cls, fact: ConstraintFact) -> TileExecutionResult:
        tile = tile_cls()
        return tile.execute(fact)

    def _record_pressure(
        self,
        goal: Goal,
        contract: TileContract,
        result: TileExecutionResult,
        ratio: float,
    ) -> PressureSignal:
        signal_id = f"pressure::{goal.goal_id}::{contract.tile_id}"
        signal = PressureSignal(
            signal_id=signal_id,
            proof_id=self._build_proof_id(goal.goal_id, contract.tile_id),
            goal_id=goal.goal_id,
            tile_id=contract.tile_id,
            metric="operation_units",
            observed_value=result.work_metrics.get("operation_units", 0.0),
            contract_budget=contract.resource_budget.get("cpu_percent", 1.0),
            pressure_ratio=ratio,
        )
        self._substrate.record_pressure_signal(signal)
        severity = "severe" if ratio >= 2.5 else "warning"
        self._substrate.record_alert(signal, severity)
        return signal

    @staticmethod
    def _build_alert_view(signal: PressureSignal) -> Dict[str, object]:
        severity = "severe" if signal.pressure_ratio >= 2.5 else "warning"
        return {
            "type": "pressure_alert",
            "signal_id": signal.signal_id,
            "tile_id": signal.tile_id,
            "severity": severity,
            "pressure_ratio": signal.pressure_ratio,
        }

    @staticmethod
    def _build_alert_panel_view(goal: Goal, signal: PressureSignal) -> Dict[str, object]:
        return {
            "type": "alert_panel",
            "goal_id": goal.goal_id,
            "signal_id": signal.signal_id,
            "severity": "severe" if signal.pressure_ratio >= 2.5 else "warning",
        }

    @staticmethod
    def _summarize_pressure(signals: List[PressureSignal], hop_metrics: List[Dict[str, object]]) -> Dict[str, object]:
        if not hop_metrics:
            return {}
        max_ratio = max(metric.get("ratio", 0.0) for metric in hop_metrics)
        status = "pressure_detected" if max_ratio > 1.0 else "within_budget"
        signal_id = signals[0].signal_id if signals else None
        return {
            "status": status,
            "ratio": max_ratio,
            "signal_id": signal_id,
            "tile_id": signals[0].tile_id if signals else None,
            "metric": signals[0].metric if signals else None,
            "observed_value": signals[0].observed_value if signals else None,
            "contract_budget": signals[0].contract_budget if signals else None,
        }

    @staticmethod
    def _build_result_summary(last_fact: ConstraintFact, tile_sequence: List[TileInvocation]) -> Dict[str, object]:
        if not tile_sequence:
            return {
                "status": "rejected",
                "reason": "no tiles executed",
                "error_code": "capability_not_found",
            }
        return {
            "status": "completed",
            "outputs": [last_fact.payload],
        }

    def _append_chain_quality(self, proof: ProofRecord) -> None:
        evaluator = ProofEvaluatorTile()
        proof_fact = ConstraintFact(
            fact_id=proof.proof_id,
            fact_type="substrate.proof_record",
            payload={
                "proof_id": proof.proof_id,
                "hop_metrics": proof.resource_usage.get("hop_metrics", []),
                "pressure_state": proof.resource_usage.get("pressure_state"),
                "result_summary": proof.result_summary,
                "presentation_views": proof.presentation_views,
            },
            confidence=1.0,
            ttl_seconds=600,
            provenance={"emitter_id": "resolver"},
            constraints_compliance=["I1", "I2", "I3", "I4"],
        )
        chain_result = evaluator.execute(proof_fact)
        self._substrate.upsert_fact(chain_result.fact)
        proof.presentation_views.append(
            {
                "type": "chain_quality",
                "fact_id": chain_result.fact.fact_id,
            }
        )
        proof.resource_usage["chain_quality"] = chain_result.fact.payload

    def _append_pressure_history(self, proof: ProofRecord, signals: List[PressureSignal]) -> None:
        history_tile = PressureHistorianTile()
        history_fact = ConstraintFact(
            fact_id=f"pressure.collection::{proof.proof_id}",
            fact_type="pressure.signal_collection",
            payload={
                "proof_id": proof.proof_id,
                "signals": [signal.__dict__ for signal in signals],
            },
            confidence=1.0,
            ttl_seconds=600,
            provenance={"emitter_id": "resolver"},
            constraints_compliance=["I1", "I2", "I3", "I4"],
        )
        history_result = history_tile.execute(history_fact)
        self._substrate.upsert_fact(history_result.fact)
        proof.presentation_views.append(
            {
                "type": "pressure_history",
                "fact_id": history_result.fact.fact_id,
            }
        )
        proof.resource_usage["pressure_history"] = history_result.fact.payload

    def _build_failure_proof(self, goal: Goal, exc: Exception) -> ProofRecord:
        failure = self._classify_failure(exc)
        proof = ProofRecord(
            proof_id=self._build_proof_id(goal.goal_id, "failure"),
            goal=self._serialize_goal(goal),
            constraint_context={"requested_invariants": goal.constraints},
            tile_sequence=[],
            capability_bindings=[],
            resource_usage={},
            result_summary={
                "status": "rejected",
                "reason": failure["message"],
                "error_code": failure["code"],
            },
            presentation_views=[],
            ledger_metadata={},
            audit_hash=None,
        )
        self._append_chain_quality(proof)
        self._append_pressure_history(proof, [])
        proof.audit_hash = self._hash_proof(proof)
        for view in proof.presentation_views:
            if view.get("type") == "chain_quality":
                view["audit_hash"] = proof.audit_hash
                view["proof_id"] = proof.proof_id
        return proof

    @staticmethod
    def _classify_failure(exc: Exception) -> Dict[str, str]:
        message = str(exc)
        if "fact" in message and "missing" in message:
            return {"code": "missing_fact", "message": message}
        if "no tile registered" in message:
            return {"code": "capability_not_found", "message": message}
        return {"code": "resolver_error", "message": message}

    @staticmethod
    def _select_capability(goal: Goal, contract: TileContract) -> str:
        if goal.capability_preferences:
            for preferred in goal.capability_preferences:
                if preferred in contract.capabilities:
                    return preferred
        for capability in contract.capabilities:
            if capability in (goal.capability_plan or []):
                return capability
        return contract.capabilities[0]

    @staticmethod
    def _hash_proof(proof: ProofRecord) -> str:
        payload = {
            "proof_id": proof.proof_id,
            "goal": proof.goal,
            "constraint_context": proof.constraint_context,
            "tile_sequence": [
                {
                    "tile_id": invocation.tile_id,
                    "inputs": invocation.inputs,
                    "outputs": invocation.outputs,
                }
                for invocation in proof.tile_sequence
            ],
            "capability_bindings": proof.capability_bindings,
            "resource_usage": proof.resource_usage,
            "result_summary": proof.result_summary,
        }
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
        return f"hash://sha256/{digest}"

    @staticmethod
    def _build_proof_id(goal_id: str, tile_id: str) -> str:
        return f"proof::{goal_id}::{tile_id}"

    @staticmethod
    def _serialize_goal(goal: Goal) -> Dict[str, object]:
        return {
            "goal_id": goal.goal_id,
            "desired_output": goal.desired_output,
            "inputs": goal.input_fact_ids,
        }
