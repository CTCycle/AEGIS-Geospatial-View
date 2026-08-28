from __future__ import annotations

from server.contracts.extraction import (
    ConversationContextSnapshot,
    LocationSignal,
    NormalizedAction,
    OverlayCommand,
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
    overlay_commands: list[OverlayCommand] | None = None,
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
        overlay_commands=overlay_commands or [],
        requested_basemap=basemap,
        tools_needed=True,
    )

###############################################################################
def test_location_only_map_does_not_invent_a_basemap_in_the_planner() -> None:
    plan = DeterministicToolPlanner().build_plan(_turn("Show Rome"), "place_resolution")
    assert plan.steps == []
    assert plan.visualization_update == {}

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
def test_typed_capability_is_selected_without_prose_keyword_inference() -> None:
    plan = DeterministicToolPlanner().build_plan(
        _turn(
            "An unrelated wording variant",
            task_class="direct_query",
            layers=["openmeteo_air_quality_forecast"],
        ),
        "environmental_data",
    )
    assert [step.capability_id for step in plan.steps] == [
        "openmeteo_air_quality_forecast"
    ]

###############################################################################
def test_basemap_replacement_is_deterministic() -> None:
    plan = DeterministicToolPlanner().build_plan(
        _turn("Switch to satellite view", basemap="esri_world_imagery"),
        "visualization_update",
    )
    assert plan.steps == []
    assert plan.visualization_update == {"basemap_replacement": "esri_world_imagery"}


###############################################################################
def test_non_additive_overlay_command_does_not_emit_provider_layer_addition() -> None:
    plan = DeterministicToolPlanner().build_plan(
        _turn(
            "Hide weather in this area",
            layers=["openmeteo_weather_forecast"],
            overlay_commands=[
                OverlayCommand(action="hide", selector={"concepts": ["weather"]}),
            ],
        ),
        "environmental_data",
    )

    assert plan.steps == []
    assert "add_layer_ids" not in plan.visualization_update
    assert "overlay_commands" in plan.visualization_update
