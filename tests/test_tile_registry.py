import pytest

from runtime.tile_registry import TileRegistry, TileContract


def test_register_tile() -> None:
    registry = TileRegistry()
    contract = TileContract(
        tile_id="tile.example",
        capabilities=["demo"],
        resource_budget={"cpu_percent": 10},
        input_types=["input.demo"],
        output_types=["output.demo"],
    )
    registry.register(contract)
    stored = registry.get("tile.example")
    assert stored.capabilities == ["demo"]


def test_register_rejects_high_cpu() -> None:
    registry = TileRegistry()
    contract = TileContract(
        tile_id="tile.over",
        capabilities=[],
        resource_budget={"cpu_percent": 31},
    )
    with pytest.raises(ValueError):
        registry.register(contract)


def test_find_by_capability() -> None:
    registry = TileRegistry()
    contract = TileContract(
        tile_id="tile.route",
        capabilities=["conversation.route_decision", "cap.edge.ultrabook"],
        resource_budget={"cpu_percent": 10},
        input_types=["conversation.turn"],
        output_types=["conversation.route_decision"],
    )
    registry.register(contract)
    found = registry.find_by_capability("conversation.route_decision")
    assert found.tile_id == "tile.route"

    with pytest.raises(ValueError):
        registry.find_by_capability("unknown.capability")


def test_list_tiles() -> None:
    registry = TileRegistry()
    first = TileContract(
        tile_id="tile.one",
        capabilities=["cap.a"],
        resource_budget={"cpu_percent": 5},
        input_types=["input.a"],
        output_types=["output.a"],
    )
    second = TileContract(
        tile_id="tile.two",
        capabilities=["cap.b"],
        resource_budget={"cpu_percent": 5},
        input_types=["input.b"],
        output_types=["output.b"],
    )
    registry.register(first)
    registry.register(second)
    tiles = registry.list_tiles()
    assert {tile.tile_id for tile in tiles} == {"tile.one", "tile.two"}
