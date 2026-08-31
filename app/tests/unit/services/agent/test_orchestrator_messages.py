from server.contracts.geospatial import (
    MapSession,
    OverlayCollectionState,
    OverlayInstance,
    ViewportPolicy,
)
from server.domain.agent.decision import ResolvedLocation
from server.services.agent.orchestrator import AgentOrchestrator
from server.services.agent.turn_support import AgentTurnSupport


###############################################################################
def _map_session(
    *,
    location: str,
    basemap_id: str = "osm_default",
    basemap_label: str | None = None,
    overlays: list[tuple[str, str, bool]] | None = None,
    warnings: list[str] | None = None,
) -> MapSession:
    return MapSession(
        session_id="map-1",
        resolved_location=ResolvedLocation(
            label=location,
            latitude=41.9028,
            longitude=12.4964,
        ),
        basemap_id=basemap_id,
        viewport=ViewportPolicy(
            center_latitude=41.9028,
            center_longitude=12.4964,
        ),
        basemap=(
            {"id": basemap_id, "label": basemap_label}
            if basemap_label is not None
            else None
        ),
        compliance_warnings=warnings or [],
        overlay_collection=OverlayCollectionState(
            instances=[
                OverlayInstance(
                    instance_id=f"instance-{index}",
                    capability_id=capability_id,
                    label=label,
                    provider="test",
                    overlay_type="overlay",
                    rendering_mode="metadata-only",
                    visible=visible,
                )
                for index, (capability_id, label, visible) in enumerate(overlays or [])
            ]
        ),
    )


###############################################################################
def test_map_session_message_uses_human_readable_labels() -> None:
    message = AgentOrchestrator._compose_map_session_message(
        _map_session(
            location="Times Square, New York",
            basemap_label="OpenStreetMap",
            overlays=[("tomtom_traffic_flow", "TomTom Traffic Flow", True)],
        )
    )

    assert message == (
        "Map ready for Times Square, New York using OpenStreetMap. "
        "Visible overlays: the TomTom Traffic Flow overlay."
    )
    assert "osm_default" not in message
    assert "tomtom_traffic_flow" not in message


###############################################################################
def test_map_session_message_humanizes_missing_label_fallbacks() -> None:
    message = AgentOrchestrator._compose_map_session_message(
        _map_session(
            location="Rome",
            overlays=[
                (
                    "rainviewer_precipitation_radar",
                    "",
                    True,
                )
            ],
        )
    )

    assert "OpenStreetMap" in message
    assert "Rainviewer Precipitation Radar" in message
    assert "osm_default" not in message
    assert "rainviewer_precipitation_radar" not in message


###############################################################################
def test_map_session_message_includes_readable_warnings() -> None:
    message = AgentOrchestrator._compose_map_session_message(
        _map_session(
            location="Shibuya Crossing",
            basemap_label="OpenStreetMap",
            overlays=[("tomtom_traffic_flow", "TomTom Traffic Flow", True)],
            warnings=[
                "tomtom_traffic_flow: A saved credential for 'tomtom' is required to render this provider tile layer.",
            ],
        )
    )

    assert "Some requested map data needs attention:" in message
    assert (
        "TomTom Traffic Flow: A saved credential for 'tomtom' is required to render this provider tile layer."
        in message
    )
    assert "TOMTOM_API_KEY" not in message


###############################################################################
def test_map_session_message_reports_current_visibility_state() -> None:
    message = AgentOrchestrator._compose_map_session_message(
        _map_session(
            location="Zurich",
            basemap_label="OpenStreetMap",
            overlays=[
                ("weather-zurich", "Weather Forecast", False),
                ("traffic-zurich", "Traffic", True),
            ],
        )
    )

    assert "Visible overlays: the Traffic overlay." in message
    assert "Hidden overlays: the Weather Forecast overlay." in message
    assert "I added" not in message


###############################################################################
def test_direct_coordinate_message_includes_coordinates() -> None:
    message = AgentOrchestrator._compose_direct_tool_message(
        "location_to_coordinates",
        {
            "location": {
                "label": "Shibuya Crossing",
                "latitude": 35.6594951,
                "longitude": 139.7004982,
            },
            "result": {
                "tool": "location_to_coordinates",
                "location": "Shibuya Crossing",
                "coordinates": {
                    "latitude": 35.6594951,
                    "longitude": 139.7004982,
                },
            },
        },
    )

    assert message == "Coordinates for Shibuya Crossing: 35.659495, 139.700498."
    assert "Executed direct tool" not in message


###############################################################################
def test_direct_weather_message_summarizes_current_conditions() -> None:
    message = AgentOrchestrator._compose_direct_tool_message(
        "get_weather_forecast",
        {
            "location": {"label": "Naples"},
            "result": {
                "tool": "get_weather_forecast",
                "location": "Naples",
                "result": {
                    "current": {
                        "time": "2026-04-24T18:45",
                        "temperature_2m": 18.6,
                        "precipitation": 0,
                    },
                },
            },
        },
    )

    assert (
        message
        == "Weather for Naples at 2026-04-24T18:45: temperature 18.6 C, precipitation 0 mm."
    )
    assert "Executed direct tool" not in message


###############################################################################
def test_parser_runtime_failure_message_is_actionable() -> None:

    ###############################################################################
    class _TurnContract:
        ambiguities = ["parser_unavailable"]

    assert AgentOrchestrator._has_parser_runtime_failure(_TurnContract())


###############################################################################
def test_provider_parser_failure_is_terminal_even_after_heuristic_extraction() -> None:

    ###############################################################################
    class _TurnContract:
        ambiguities = ["provider_authentication_failed"]
        task_class = "map_search"

    assert AgentOrchestrator._has_parser_runtime_failure(_TurnContract())


###############################################################################
def test_typed_context_query_can_answer_previous_user_request() -> None:
    message = AgentTurnSupport.compose_context_query_message(
        "previous_user_request",
        [
            {"role": "user", "content": "Show me Rome"},
            {"role": "assistant", "content": "Map ready for Rome."},
        ],
    )

    assert message == "You just asked: Show me Rome"


###############################################################################
def test_typed_context_query_can_answer_active_map_location() -> None:
    message = AgentTurnSupport.compose_context_query_message(
        "active_location",
        [],
        {"active_location": {"label": "Lugano"}},
    )

    assert message == "The map is currently centered on Lugano."


###############################################################################
def test_typed_context_query_accepts_active_map_location() -> None:
    message = AgentTurnSupport.compose_context_query_message(
        "active_location",
        [],
        {"active_location": {"label": "Zurich"}},
    )

    assert message == "The map is currently centered on Zurich."


###############################################################################
def test_typed_context_query_can_answer_active_map_overlays() -> None:
    message = AgentTurnSupport.compose_context_query_message(
        "active_overlays",
        [],
        {
            "active_visualization": {
                "overlay_collection": {
                    "instances": [
                        {
                            "instance_id": "air-quality-1",
                            "capability_id": "openmeteo_air_quality_forecast",
                            "label": "Open-Meteo Air Quality Forecast",
                        },
                    ],
                },
            }
        },
    )

    assert message == (
        "The current map includes these overlays: Open-Meteo Air Quality Forecast."
    )


###############################################################################
def test_typed_context_query_can_summarize_active_map_with_overlays() -> None:
    message = AgentTurnSupport.compose_context_query_message(
        "active_map_summary",
        [],
        {
            "active_visualization": {
                "resolved_location": {"label": "Zurich"},
                "basemap": {"label": "Satellite Imagery"},
                "overlay_collection": {"instances": []},
            }
        },
    )

    assert message == (
        "The map is centered on Zurich using Satellite Imagery. "
        "The current map has no overlays requested."
    )


###############################################################################
def test_typed_context_query_can_summarize_active_map() -> None:
    message = AgentTurnSupport.compose_context_query_message(
        "active_map_summary",
        [],
        {
            "active_visualization": {
                "resolved_location": {"label": "Athens, Greece"},
                "basemap": {"label": "OpenStreetMap"},
                "overlay_collection": {
                    "instances": [
                        {
                            "instance_id": "air-quality-1",
                            "capability_id": "openmeteo_air_quality_forecast",
                            "label": "Open-Meteo Air Quality Forecast",
                        },
                    ],
                },
            }
        },
    )

    assert message == (
        "The map is centered on Athens, Greece using OpenStreetMap. "
        "The current map includes these overlays: Open-Meteo Air Quality Forecast."
    )
