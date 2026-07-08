from __future__ import annotations

from server.domain.extraction.models import (
    ConversationContextSnapshot,
    LocationSignal,
    NormalizedAction,
    TurnParseResult,
)
from server.services.agent.tool_planner import DeterministicToolPlanner

###############################################################################
def _turn(
    text: str,
    *,
    task_class: str = "map_search",
    layers: list[str] | None = None,
    basemap: str | None = None,
) -> TurnParseResult:
    return TurnParseResult(
        user_text=text,
        conversation_context=ConversationContextSnapshot(),
        task_class=task_class,
        location_signals=[
            LocationSignal(
                signal_type="city",
                raw_value="Rome",
                normalized_value="Rome",
                latitude=41.9028,
                longitude=12.4964,
                confidence=0.99,
            )
        ],
        normalized_action=NormalizedAction(
            action_id="map_search",
            action_label="Map search",
            requires_location=True,
        ),
        parser_confidence=0.95,
        requested_layers=layers or [],
        requested_basemap=basemap,
        tools_needed=True,
    )

###############################################################################
def test_location_only_map_uses_deterministic_visualization_update() -> None:
    plan = DeterministicToolPlanner().build_plan(_turn("Show Rome"), "place_resolution")
    assert plan.steps == []
    assert plan.visualization_update == {"basemap_replacement": "osm_default"}

###############################################################################
def test_layer_plan_contains_location_arguments() -> None:
    plan = DeterministicToolPlanner().build_plan(
        _turn("Show rain radar over Rome", layers=["rainviewer_precipitation_radar"]),
        "environmental_data",
    )
    assert plan.steps[0].arguments["capability_id"] == "rainviewer_precipitation_radar"
    assert plan.steps[0].arguments["arguments"]["location"] == "Rome"

###############################################################################
def test_provider_layer_selection_uses_provider_render_tool() -> None:
    plan = DeterministicToolPlanner().build_plan(
        _turn("Render the selected GIBS layer over Rome", layers=["gibs:MODIS_Terra_CorrectedReflectance_TrueColor"]),
        "map_layers",
    )

    assert [step.tool_name for step in plan.steps] == ["render_geospatial_provider_layer"]
    assert plan.steps[0].arguments == {
        "provider_id": "gibs",
        "layer_id": "MODIS_Terra_CorrectedReflectance_TrueColor",
    }

###############################################################################
def test_air_quality_forecast_selects_direct_capability() -> None:
    plan = DeterministicToolPlanner().build_plan(
        _turn("Get air quality forecast for Milan", task_class="direct_query"),
        "environmental_data",
    )
    assert [step.capability_id for step in plan.steps] == ["get_air_quality_forecast"]

###############################################################################
def test_basemap_replacement_is_deterministic() -> None:
    plan = DeterministicToolPlanner().build_plan(
        _turn("Switch to satellite view", basemap="esri_world_imagery"),
        "visualization_update",
    )
    assert plan.steps == []
    assert plan.visualization_update == {"basemap_replacement": "esri_world_imagery"}
