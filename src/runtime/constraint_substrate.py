"""Deterministic data models and stubs aligned with substrate_contracts.json."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

ISO_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def _timestamp() -> str:
    """Return an ISO-8601 timestamp in UTC without randomness."""
    return datetime.now(timezone.utc).strftime(ISO_FORMAT)


@dataclass
class ConstraintFact:
    fact_id: str
    fact_type: str
    payload: Dict[str, Any]
    confidence: float
    ttl_seconds: int
    provenance: Dict[str, Any]
    constraints_compliance: List[str]
    created_timestamp: str = field(default_factory=_timestamp)


@dataclass
class CapabilityDescriptor:
    capability_id: str
    resource_class: str
    hardware_traits: Dict[str, Any]
    latency_profile_ms: Dict[str, int]
    privacy_guarantees: Dict[str, Any]
    current_utilization_percent: Dict[str, float]


@dataclass
class TileInvocation:
    tile_id: str
    inputs: List[str]
    outputs: List[str]


@dataclass
class ProofRecord:
    proof_id: str
    goal: Dict[str, Any]
    constraint_context: Dict[str, Any]
    tile_sequence: List[TileInvocation]
    capability_bindings: List[Dict[str, str]]
    resource_usage: Dict[str, float]
    result_summary: Dict[str, Any]
    presentation_views: List[Dict[str, Any]]
    ledger_metadata: Dict[str, Any] = field(default_factory=dict)
    audit_hash: Optional[str] = None


@dataclass
class PressureSignal:
    signal_id: str
    proof_id: str
    goal_id: str
    tile_id: str
    metric: str
    observed_value: float
    contract_budget: float
    pressure_ratio: float


class ConstraintSubstrate:
    """In-memory substrate stub for future expansion."""

    def __init__(self) -> None:
        self._facts: Dict[str, ConstraintFact] = {}
        self._proofs: Dict[str, ProofRecord] = {}
        self._pressure_signals: Dict[str, PressureSignal] = {}
        self._alerts: Dict[str, Dict[str, Any]] = {}

    def upsert_fact(self, fact: ConstraintFact) -> None:
        if fact.confidence < 0.0 or fact.confidence > 1.0:
            raise ValueError("confidence must be between 0 and 1")
        self._facts[fact.fact_id] = fact

    def get_fact(self, fact_id: str) -> Optional[ConstraintFact]:
        return self._facts.get(fact_id)

    def record_proof(self, proof: ProofRecord) -> None:
        self._proofs[proof.proof_id] = proof

    def get_proof(self, proof_id: str) -> Optional[ProofRecord]:
        return self._proofs.get(proof_id)

    def record_pressure_signal(self, signal: PressureSignal) -> None:
        self._pressure_signals[signal.signal_id] = signal

    def get_pressure_signal(self, signal_id: str) -> Optional[PressureSignal]:
        return self._pressure_signals.get(signal_id)

    def list_pressure_signals(self) -> List[PressureSignal]:
        return list(self._pressure_signals.values())

    def pressure_summary(self) -> Dict[str, Any]:
        summary = {
            "pressure_detected": 0,
            "within_budget": 0,
            "total": 0,
            "max_ratio": 0.0,
            "tiles": {},
            "alerts": {
                "warning": 0,
                "severe": 0,
            },
        }
        for signal in self._pressure_signals.values():
            summary["pressure_detected"] += 1
            summary["total"] += 1
            summary["max_ratio"] = max(summary["max_ratio"], signal.pressure_ratio)
            summary["tiles"].setdefault(signal.tile_id, 0)
            summary["tiles"][signal.tile_id] += 1
        for alert in self._alerts.values():
            summary["alerts"].setdefault(alert["severity"], 0)
            summary["alerts"][alert["severity"]] += 1
        return summary

    def pressure_alerts(self, ratio_threshold: float = 2.0) -> List[PressureSignal]:
        return [signal for signal in self._pressure_signals.values() if signal.pressure_ratio >= ratio_threshold]

    def record_alert(self, signal: PressureSignal, severity: str) -> None:
        alert_id = f"alert::{signal.signal_id}"
        self._alerts[alert_id] = {
            "alert_id": alert_id,
            "signal_id": signal.signal_id,
            "tile_id": signal.tile_id,
            "pressure_ratio": signal.pressure_ratio,
            "severity": severity,
        }

    def list_alerts(self) -> List[Dict[str, Any]]:
        return list(self._alerts.values())

    def build_ledger_entry(self, proof_id: str) -> Dict[str, Any]:
        proof = self.get_proof(proof_id)
        if proof is None:
            raise ValueError(f"proof {proof_id} not found")
        pressure_state = proof.resource_usage.get("pressure_state")
        alerts = []
        signals = []
        presentation_alerts = [
            view
            for view in proof.presentation_views
            if view.get("type") == "pressure_alert"
        ]
        alert_panel_views = [
            view
            for view in proof.presentation_views
            if view.get("type") == "alert_panel"
        ]
        chain_quality_views = [
            view
            for view in proof.presentation_views
            if view.get("type") == "chain_quality"
        ]
        chain_quality_fact = None
        if chain_quality_views:
            fact_id = chain_quality_views[0].get("fact_id")
            if fact_id:
                fact = self.get_fact(fact_id)
                if fact:
                    chain_quality_fact = {
                        "fact_id": fact.fact_id,
                        "fact_type": fact.fact_type,
                        "payload": fact.payload,
                        "confidence": fact.confidence,
                        "ttl_seconds": fact.ttl_seconds,
                        "provenance": fact.provenance,
                        "constraints_compliance": fact.constraints_compliance,
                    }
        pressure_history_views = [
            view
            for view in proof.presentation_views
            if view.get("type") == "pressure_history"
        ]
        pressure_history_fact = None
        if pressure_history_views:
            history_fact_id = pressure_history_views[0].get("fact_id")
            if history_fact_id:
                history_fact = self.get_fact(history_fact_id)
                if history_fact:
                    pressure_history_fact = {
                        "fact_id": history_fact.fact_id,
                        "fact_type": history_fact.fact_type,
                        "payload": history_fact.payload,
                        "confidence": history_fact.confidence,
                        "ttl_seconds": history_fact.ttl_seconds,
                        "provenance": history_fact.provenance,
                        "constraints_compliance": history_fact.constraints_compliance,
                    }
        if pressure_state and pressure_state.get("signal_id"):
            alerts = [
                alert
                for alert in sorted(self._alerts.values(), key=lambda item: item["alert_id"])
                if alert["signal_id"] == pressure_state["signal_id"]
            ]
            signal = self.get_pressure_signal(pressure_state["signal_id"])
            if signal:
                signals.append(signal.__dict__)
        return {
            "proof_id": proof.proof_id,
            "goal": proof.goal,
            "resource_usage": proof.resource_usage,
            "pressure_state": pressure_state,
            "ledger_metadata": proof.ledger_metadata,
            "pressure_alerts": alerts,
            "presentation_alerts": presentation_alerts,
            "alert_panel_views": alert_panel_views,
            "chain_quality_view": chain_quality_views[0] if chain_quality_views else None,
            "chain_quality_fact": chain_quality_fact,
            "pressure_history_view": pressure_history_views[0] if pressure_history_views else None,
            "pressure_history_fact": pressure_history_fact,
            "signals": signals,
        }

    def export_pressure_report(self) -> Dict[str, Any]:
        pressure_alerts = sorted(self._alerts.values(), key=lambda item: item["alert_id"])
        return {
            "summary": self.pressure_summary(),
            "signals": [
                signal.__dict__
                for signal in sorted(self._pressure_signals.values(), key=lambda item: item.signal_id)
            ],
            "pressure_alerts": pressure_alerts,
            "alerts": pressure_alerts,
        }
