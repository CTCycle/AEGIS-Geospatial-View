from server.services.agent.orchestrator import AgentOrchestrator

###############################################################################
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

###############################################################################
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

###############################################################################
def test_map_session_message_includes_readable_warnings() -> None:
    message = AgentOrchestrator._compose_map_session_message(
        {
            "resolved_location": {"label": "Shibuya Crossing"},
            "basemap_id": "osm_default",
            "basemap": {"id": "osm_default", "label": "OpenStreetMap"},
            "overlay_ids": ["tomtom_traffic_flow"],
            "overlays": [{"id": "tomtom_traffic_flow", "label": "TomTom Traffic Flow"}],
            "compliance_warnings": [
                "tomtom_traffic_flow: TOMTOM_API_KEY is required to render this provider tile layer.",
            ],
        },
    )

    assert "Some requested map data needs attention:" in message
    assert "TomTom Traffic Flow: TomTom API key is required to render this provider tile layer." in message
    assert "TOMTOM_API_KEY" not in message


def test_map_session_message_reports_current_visibility_state() -> None:
    message = AgentOrchestrator._compose_map_session_message(
        {
            "resolved_location": {"label": "Zurich"},
            "basemap_id": "osm_default",
            "basemap": {"id": "osm_default", "label": "OpenStreetMap"},
            "overlay_ids": ["weather-zurich", "traffic-zurich"],
            "overlays": [
                {"id": "weather-zurich", "label": "Weather Forecast", "visible": False},
                {"id": "traffic-zurich", "label": "Traffic", "visible": True},
            ],
            "compliance_warnings": [],
        },
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

    assert message == "Weather for Naples at 2026-04-24T18:45: temperature 18.6 C, precipitation 0 mm."
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
def test_general_question_can_answer_previous_user_request() -> None:
    message = AgentOrchestrator._compose_general_question_message(
        "What did I just ask?",
        [
            {"role": "user", "content": "Show me Rome"},
            {"role": "assistant", "content": "Map ready for Rome."},
            {"role": "user", "content": "What did I just ask?"},
        ],
    )

    assert message == "You just asked: Show me Rome"

###############################################################################
def test_general_question_can_answer_active_map_location() -> None:
    message = AgentOrchestrator._compose_general_question_message(
        "What city is the map centered on?",
        [],
        {"active_location": {"label": "Lugano"}},
    )

    assert message == "The map is currently centered on Lugano."

###############################################################################
def test_general_question_accepts_which_city_variant() -> None:
    message = AgentOrchestrator._compose_general_question_message(
        "Which city is the map centered on?",
        [],
        {"active_location": {"label": "Zurich"}},
    )

    assert message == "The map is currently centered on Zurich."

###############################################################################
def test_general_question_can_answer_active_map_overlays() -> None:
    message = AgentOrchestrator._compose_general_question_message(
        "What overlays are currently requested?",
        [],
        {
            "active_visualization": {
                "overlay_ids": ["openmeteo_air_quality_forecast"],
                "overlays": [
                    {
                        "id": "openmeteo_air_quality_forecast",
                        "label": "Open-Meteo Air Quality Forecast",
                    }
                ],
            }
        },
    )

    assert message == (
        "The current map includes these overlays: Open-Meteo Air Quality Forecast."
    )

###############################################################################
def test_general_question_can_summarize_active_map() -> None:
    message = AgentOrchestrator._compose_general_question_message(
        "Summarize the current map.",
        [],
        {
            "active_visualization": {
                "resolved_location": {"label": "Zurich"},
                "basemap": {"label": "Satellite Imagery"},
                "overlay_ids": [],
            }
        },
    )

    assert message == (
        "The map is centered on Zurich using Satellite Imagery. "
        "The current map has no overlays requested."
    )

###############################################################################
def test_general_question_can_summarize_interesting_areas_from_active_map() -> None:
    message = AgentOrchestrator._compose_general_question_message(
        "Now summarize the three most interesting areas.",
        [],
        {
            "active_visualization": {
                "resolved_location": {"label": "Athens, Greece"},
                "basemap": {"label": "OpenStreetMap"},
                "overlay_ids": ["openmeteo_air_quality_forecast"],
                "overlays": [
                    {
                        "id": "openmeteo_air_quality_forecast",
                        "label": "Open-Meteo Air Quality Forecast",
                    }
                ],
            }
        },
    )

    assert message == (
        "The map is centered on Athens, Greece using OpenStreetMap. "
        "The current map includes these overlays: Open-Meteo Air Quality Forecast."
    )
