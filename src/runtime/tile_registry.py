"""Tile registry stub bound to reasoning_tile_contract schemas."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Protocol


class ExecutionContext(Protocol):
    def emit_fact(self, fact_type: str, payload: Dict[str, object]) -> None:
        ...


@dataclass
class TileContract:
    tile_id: str
    capabilities: List[str]
    resource_budget: Dict[str, float]
    input_types: List[str] = field(default_factory=list)
    output_types: List[str] = field(default_factory=list)


class TileRegistry:
    """Lightweight registry to hold tile contracts before full implementation."""

    def __init__(self) -> None:
        self._tiles: Dict[str, TileContract] = {}

    def register(self, contract: TileContract) -> None:
        if contract.tile_id in self._tiles:
            raise ValueError(f"tile {contract.tile_id} already registered")
        if contract.resource_budget.get("cpu_percent", 0) > 30:
            raise ValueError("cpu_percent exceeds policy ceiling")
        self._tiles[contract.tile_id] = contract

    def get(self, tile_id: str) -> TileContract:
        return self._tiles[tile_id]

    def find_by_capability(self, capability: str) -> TileContract:
        for contract in self._tiles.values():
            if capability in contract.capabilities:
                return contract
        raise ValueError(f"no tile registered for capability {capability}")

    def find_all_by_capability(self, capability: str) -> List[TileContract]:
        return [contract for contract in self._tiles.values() if capability in contract.capabilities]

    def list_tiles(self) -> List[TileContract]:
        return list(self._tiles.values())
