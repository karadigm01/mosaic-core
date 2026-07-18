from __future__ import annotations

import json
from pathlib import Path

import pytest

from runtime import macro_tile_generator


def test_register_macro_tile_doc_requires_promoted(tmp_path: Path) -> None:
    doc = tmp_path / "macro_doc.json"
    payload = {
        "contract": {"lifecycle_state": "sandboxed"},
    }
    doc.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="promoted"):
        macro_tile_generator.register_macro_tile_doc(doc, tmp_path / "component_index.json")


def test_register_macro_tile_doc_invokes_registration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    doc = tmp_path / "macro_doc.json"
    payload = {
        "component_id": "tile.macro.demo",
        "component_name": "Demo Macro Tile",
        "component_type": "runtime_module",
        "contract": {"lifecycle_state": "promoted"},
    }
    doc.write_text(json.dumps(payload), encoding="utf-8")

    called: dict = {}

    def _fake_register(component_path: Path, index_path: Path, workspace_root: Path | None):
        called["args"] = (component_path, index_path, workspace_root)
        return {"components": []}

    monkeypatch.setattr(macro_tile_generator.component_registry_sync, "register_component", _fake_register)

    result = macro_tile_generator.register_macro_tile_doc(
        doc,
        tmp_path / "component_index.json",
        workspace_root=tmp_path,
    )
    assert called["args"][0] == doc
    assert called["args"][1].name == "component_index.json"
    assert called["args"][2] == tmp_path
    assert result == {"components": []}
