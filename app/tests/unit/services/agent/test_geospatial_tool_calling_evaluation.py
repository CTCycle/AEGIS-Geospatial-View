from __future__ import annotations

import pytest

from server.contracts.extraction import (
    ConversationContextSnapshot,
    LocationSignal,
    NormalizedAction,
    TemporalSignal,
    TurnParseResult,
)
from server.services.agent.tool_planner import DeterministicToolPlanner


###############################################################################
def _turn(
    text: str,
    *,
    task_class: str = "map_search",
    location: str = "Rome",
    layers: list[str] | None = None,
    basemap: str | None = None,
    entity: str | None = None,
    temporal: TemporalSignal | None = None,
    required_data_sources: list[str] | None = None,
    required_tool_category: str | None = None,
    tools_needed: bool = True,
) -> TurnParseResult:
    return TurnParseResult(
        user_text=text,
        conversation_context=ConversationContextSnapshot(),
        task_class=task_class,
        location_signals=[
            LocationSignal(
                signal_type="city",
                raw_value=location,
                normalized_value=location,
                latitude=41.9028,
                longitude=12.4964,
                confidence=0.99,
            )
        ]
        if location
        else [],
        normalized_action=NormalizedAction(
            action_id="map_search",
            action_label="Map search",
            requires_location=bool(location),
        ),
        temporal_signal=temporal or TemporalSignal(),
        parser_confidence=0.95,
        requested_layers=layers or [],
        requested_basemap=basemap,
        entity_target=entity,
        required_data_sources=required_data_sources or [],
        required_tool_category=required_tool_category,
        tools_needed=tools_needed,
    )


###############################################################################
@pytest.mark.parametrize(
    ("name", "turn", "specialist", "memory", "expected_tools", "expected_capabilities"),
    [
        (
            "direct_location",
            _turn("Show Rome on the map", task_class="map_search"),
            "place_resolution",
            None,
            [],
            [],
        ),
        (
            "coordinate_lookup",
            _turn(
                "Find the coordinates for Rome",
                task_class="direct_query",
                layers=["location_to_coordinates"],
            ),
            "place_resolution",
            None,
            ["execute_geospatial_capability"],
            ["location_to_coordinates"],
        ),
        (
            "bbox_layer",
            _turn(
                "Show demographics in the current bounding box",
                layers=["census_tigerweb_demographics"],
            ),
            "map_layers",
            {"bbox": [-74.1, 40.6, -73.8, 40.9]},
            ["execute_geospatial_capability"],
            ["census_tigerweb_demographics"],
        ),
        (
            "environmental_forecast",
            _turn(
                "Give me the weather forecast for Milan",
                task_class="direct_query",
                layers=["get_weather_forecast"],
            ),
            "environmental_data",
            None,
            ["execute_geospatial_capability"],
            ["get_weather_forecast"],
        ),
        (
            "air_quality_forecast",
            _turn(
                "Give me the air quality forecast for Milan",
                task_class="direct_query",
                layers=["get_air_quality_forecast"],
            ),
            "environmental_data",
            None,
            ["execute_geospatial_capability"],
            ["get_air_quality_forecast"],
        ),
        (
            "poi_query",
            _turn(
                "Find nearby hospitals in Rome",
                task_class="direct_query",
                entity="hospitals",
                layers=["get_nearby_poi"],
            ),
            "geospatial_features",
            None,
            ["execute_geospatial_capability"],
            ["get_nearby_poi"],
        ),
        (
            "provider_native_imagery",
            _turn(
                "Render satellite imagery over Rome",
                layers=["gibs:MODIS_Terra_CorrectedReflectance_TrueColor"],
            ),
            "map_layers",
            None,
            ["render_geospatial_provider_layer"],
            [],
        ),
        (
            "time_sensitive_layer",
            _turn(
                "Show rainfall from yesterday",
                layers=["rainviewer_precipitation_radar"],
                temporal=TemporalSignal(mode="historical", raw_text="yesterday"),
            ),
            "environmental_data",
            None,
            ["execute_geospatial_capability"],
            ["rainviewer_precipitation_radar"],
        ),
        (
            "multi_tool_request",
            _turn(
                "Show the weather and nearby cafes in Rome",
                task_class="direct_query",
                entity="cafes",
                layers=["get_weather_forecast", "get_nearby_poi"],
            ),
            "environmental_data",
            None,
            ["execute_geospatial_capability"],
            ["get_weather_forecast", "get_nearby_poi"],
        ),
        (
            "provider_discovery",
            _turn(
                "Find available layers from GIBS",
                required_data_sources=["gibs"],
                required_tool_category="provider_native_discovery",
            ),
            "map_layers",
            None,
            ["fetch_geospatial_provider_layers"],
            [],
        ),
        (
            "unsupported_or_ambiguous",
            _turn(
                "What do you think about this?",
                task_class="general_question",
                location="",
                tools_needed=False,
            ),
            "direct_chat",
            None,
            [],
            [],
        ),
    ],
)
def test_deterministic_geospatial_tool_calling_scenarios(
    name: str,
    turn: TurnParseResult,
    specialist: str,
    memory: dict | None,
    expected_tools: list[str],
    expected_capabilities: list[str],
) -> None:
    del name
    plan = DeterministicToolPlanner().build_plan(turn, specialist, memory)
    assert plan.selected_tools == expected_tools
    assert [
        step.capability_id for step in plan.steps if step.capability_id
    ] == expected_capabilities


###############################################################################
def test_bbox_evaluation_preserves_canonical_coordinate_order() -> None:
    turn = _turn(
        "Show demographics in this extent",
        location="",
        layers=["census_tigerweb_demographics"],
    )
    plan = DeterministicToolPlanner().build_plan(
        turn,
        "map_layers",
        {"bbox": [-74.1, 40.6, -73.8, 40.9]},
    )
    assert plan.steps[0].arguments["arguments"]["bbox"] == [-74.1, 40.6, -73.8, 40.9]
