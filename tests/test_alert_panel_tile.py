from runtime.alert_panel_tile import AlertPanelTile


def test_alert_panel_tile_summarizes_alerts() -> None:
    alerts = [
        {
            "signal_id": "pressure::demo",
            "tile_id": "tile.lang.semantic_router",
            "severity": "warning",
            "pressure_ratio": 2.2,
        }
    ]
    tile = AlertPanelTile()
    result = tile.execute("proof::demo", alerts)

    assert result.fact.fact_type == "presentation.alert_panel"
    assert result.fact.fact_id == "fact.alert_panel::proof::demo"
    assert result.alerts[0]["signal_id"] == "pressure::demo"
    assert result.fact.payload["alerts"][0]["severity"] == "warning"
