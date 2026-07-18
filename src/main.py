from __future__ import annotations

import argparse
import json
from typing import Any, Dict, Optional, Sequence

from runtime.constraint_substrate import ConstraintFact, ConstraintSubstrate, ProofRecord
from runtime.resolver import Goal, Resolver
from runtime.tile_registry import TileContract, TileRegistry
from runtime.sentiment_tile import SentimentTile
from runtime.semantic_router import SemanticRouterTile
from runtime.route_dispatch_tile import RouteDispatchTile
from runtime.pressure_summary_tile import PressureSummaryTile
from runtime.alert_panel_tile import AlertPanelTile
from runtime.guided_hallucinator_tile import GuidedHallucinatorTile


def _serialize_proof(proof: ProofRecord) -> Dict[str, Any]:
    return {
        "proof_id": proof.proof_id,
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
        "pressure_state": proof.resource_usage.get("pressure_state"),
        "chain_quality": proof.resource_usage.get("chain_quality"),
        "presentation_views": proof.presentation_views,
        "result_summary": proof.result_summary,
    }


def _build_sentiment_proof() -> Dict[str, Any]:
    substrate = ConstraintSubstrate()
    substrate.upsert_fact(
        ConstraintFact(
            fact_id="fact.user_text",
            fact_type="user.text_input",
            payload={"text": "I hate waiting for support"},
            confidence=1.0,
            ttl_seconds=300,
            provenance={"source": "demo"},
            constraints_compliance=["I1", "I2", "I3", "I4"],
        )
    )
    registry = TileRegistry()
    registry.register(
        TileContract(
            tile_id=SentimentTile.TILE_ID,
            capabilities=["text.sentiment"],
            resource_budget={"cpu_percent": 15},
            input_types=SentimentTile.INPUT_TYPES,
            output_types=[SentimentTile.OUTPUT_TYPE],
        )
    )
    registry.register(
        TileContract(
            tile_id=SemanticRouterTile.TILE_ID,
            capabilities=["conversation.route"],
            resource_budget={"cpu_percent": 20},
            input_types=SemanticRouterTile.INPUT_TYPES,
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
            input_types=[PressureSummaryTile.INPUT_TYPES[0]],
            output_types=[PressureSummaryTile.OUTPUT_TYPE],
        )
    )
    registry.register(
        TileContract(
            tile_id=AlertPanelTile.TILE_ID,
            capabilities=["presentation.alert_panel"],
            resource_budget={"cpu_percent": 5},
            input_types=[PressureSummaryTile.OUTPUT_TYPE],
            output_types=[AlertPanelTile.OUTPUT_TYPE],
        )
    )
    resolver = Resolver(substrate, registry)
    goal = Goal(
        goal_id="demo.sentiment",
        desired_output="pressure.summary",
        input_fact_ids=["fact.user_text"],
        constraints=["I1", "I2", "I3", "I4"],
    )
    proof = resolver.resolve(goal)
    return _serialize_proof(proof)


def _build_imagination_proof(prompt: str) -> Dict[str, Any]:
    substrate = ConstraintSubstrate()
    substrate.upsert_fact(
        ConstraintFact(
            fact_id="fact.conversation.turn",
            fact_type="conversation.turn",
            payload={"text": prompt},
            confidence=0.95,
            ttl_seconds=300,
            provenance={"source": "demo"},
            constraints_compliance=["I1", "I2", "I3", "I4"],
        )
    )
    registry = TileRegistry()
    registry.register(
        TileContract(
            tile_id=SemanticRouterTile.TILE_ID,
            capabilities=["conversation.route"],
            resource_budget={"cpu_percent": 20},
            input_types=SemanticRouterTile.INPUT_TYPES,
            output_types=[SemanticRouterTile.OUTPUT_TYPE],
        )
    )
    registry.register(
        TileContract(
            tile_id=GuidedHallucinatorTile.TILE_ID,
            capabilities=["conversation.imagination", "conversation.hypothesis"],
            resource_budget={
                "cpu_percent": 30,
                "memory_mb": 2048,
                "disk_mb": 512,
                "latency_p95_ms": 120,
            },
            input_types=GuidedHallucinatorTile.INPUT_TYPES,
            output_types=[GuidedHallucinatorTile.OUTPUT_TYPE],
        )
    )
    resolver = Resolver(substrate, registry)
    goal = Goal(
        goal_id="demo.hallucinator",
        desired_output=GuidedHallucinatorTile.OUTPUT_TYPE,
        input_fact_ids=["fact.conversation.turn"],
        constraints=["I1", "I2", "I3", "I4"],
        capability_plan=["conversation.route", "conversation.imagination"],
    )
    proof = resolver.resolve(goal)
    return _serialize_proof(proof)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Demo entry point for resolver proofs")
    parser.add_argument(
        "--demo",
        choices=["sentiment", "imagination"],
        default="sentiment",
        help="Choose which resolver chain to execute",
    )
    parser.add_argument(
        "--prompt",
        default="Imagine a hypothesis about glass cities.",
        help="Prompt text for the imagination demo",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.demo == "imagination":
        proof = _build_imagination_proof(args.prompt)
    else:
        proof = _build_sentiment_proof()

    print(json.dumps(proof, indent=2, sort_keys=True))


def bootstrap() -> tuple[ConstraintSubstrate, TileRegistry]:
    substrate = ConstraintSubstrate()
    registry = TileRegistry()
    registry.register(
        TileContract(
            tile_id="tile.lang.semantic_router",
            capabilities=["language.route"],
            resource_budget={"cpu_percent": 20, "memory_mb": 512},
            input_types=["conversation.turn"],
            output_types=["conversation.route_decision"],
        )
    )
    return substrate, registry


if __name__ == "__main__":
    main()
