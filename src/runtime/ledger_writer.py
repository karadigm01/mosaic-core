"""Ledger writer stub for exporting proof records with pressure metadata."""
from __future__ import annotations

from typing import Dict, List

from runtime.constraint_substrate import ConstraintSubstrate


class LedgerWriter:
    """Deterministic ledger writer that serializes proofs for export."""

    def __init__(self, substrate: ConstraintSubstrate) -> None:
        self._substrate = substrate

    def export_entries(self, proof_ids: List[str]) -> List[Dict[str, object]]:
        entries: List[Dict[str, object]] = []
        for proof_id in proof_ids:
            entry = self._substrate.build_ledger_entry(proof_id)
            entries.append({
                "proof_id": entry["proof_id"],
                "resource_usage": entry["resource_usage"],
                "pressure_state": entry["pressure_state"],
                "pressure_alerts": entry.get("pressure_alerts", []),
                "presentation_alerts": entry.get("presentation_alerts", []),
                "alert_panel_views": entry.get("alert_panel_views", []),
                "chain_quality_view": entry.get("chain_quality_view"),
                "chain_quality_fact": entry.get("chain_quality_fact"),
                "pressure_history_view": entry.get("pressure_history_view"),
                "pressure_history_fact": entry.get("pressure_history_fact"),
                "ledger_metadata": entry["ledger_metadata"],
                "signals": entry.get("signals", []),
            })
        return entries

    def export_pressure_report(self) -> Dict[str, object]:
        return self._substrate.export_pressure_report()
