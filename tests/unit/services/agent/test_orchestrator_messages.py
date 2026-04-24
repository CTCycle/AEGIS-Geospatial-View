from AEGIS.server.services.agent.orchestrator import AgentOrchestrator


def test_map_session_message_uses_human_readable_labels() -> None:
    message = AgentOrchestrator._compose_map_session_message(
        {
            "resolved_location": {"label": "Times Square, New York"},
            "basemap_id": "osm_default",
            "basemap": {"id": "osm_default", "label": "OpenStreetMap"},
            "overlay_ids": ["tomtom_traffic_flow"],
            "overlays": [{"id": "tomtom_traffic_flow", "label": "TomTom Traffic Flow"}],
            "compliance_warnings": [],
        },
    )

    assert message == (
        "Map ready for Times Square, New York using OpenStreetMap. "
        "I added the TomTom Traffic Flow overlay."
    )
    assert "osm_default" not in message
    assert "tomtom_traffic_flow" not in message


def test_map_session_message_humanizes_missing_label_fallbacks() -> None:
    message = AgentOrchestrator._compose_map_session_message(
        {
            "resolved_location": {"label": "Rome"},
            "basemap_id": "osm_default",
            "overlay_ids": ["rainviewer_precipitation_radar"],
            "overlays": [],
            "compliance_warnings": [],
        },
    )

    assert "OpenStreetMap" in message
    assert "Rainviewer Precipitation Radar" in message
    assert "osm_default" not in message
    assert "rainviewer_precipitation_radar" not in message


def test_map_session_message_includes_readable_warnings() -> None:
    message = AgentOrchestrator._compose_map_session_message(
        {
            "resolved_location": {"label": "Shibuya Crossing"},
            "basemap_id": "osm_default",
            "basemap": {"id": "osm_default", "label": "OpenStreetMap"},
            "overlay_ids": ["tomtom_traffic_flow"],
            "overlays": [{"id": "tomtom_traffic_flow", "label": "TomTom Traffic Flow"}],
            "compliance_warnings": [
                "tomtom_basic: provider API key is required; falling back to osm_default.",
                "tomtom_traffic_flow: TOMTOM_API_KEY is required to render this provider tile layer.",
            ],
        },
    )

    assert "Some requested map data needs attention:" in message
    assert "TomTom Basic: provider API key is required; falling back to OpenStreetMap." in message
    assert "TomTom Traffic Flow: TomTom API key is required to render this provider tile layer." in message
    assert "tomtom_basic" not in message
    assert "TOMTOM_API_KEY" not in message
