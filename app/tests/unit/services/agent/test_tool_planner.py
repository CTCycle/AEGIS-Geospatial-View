from __future__ import annotations

from server.contracts.extraction import (
    ConversationContextSnapshot,
    LocationSignal,
    NormalizedAction,
    OverlayCommand,
    TurnParseResult,
)
from server.domain.agent.decision import ResolvedLocation
from server.services.agent.request_interpreter import RequestInterpreter
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
def test_native_location_only_map_has_catalog_owned_basemap_step() -> None:
    planner = DeterministicToolPlanner()
    turn = _turn("Show Rome")
    plan = planner.build_plan(
        turn,
        "place_resolution",
        resolved_location=ResolvedLocation(
            label="Rome, Italy", latitude=41.9028, longitude=12.4964
        ),
    )
    plan = planner.add_native_basemap_step(
        plan,
        turn,
        resolved_location=ResolvedLocation(
            label="Rome, Italy", latitude=41.9028, longitude=12.4964
        ),
    )
    assert len(plan.steps) == 1
    assert plan.steps[0].capability_id == "osm_default"
    assert plan.steps[0].arguments["arguments"]["location"] == "Rome, Italy"

###############################################################################
def test_layer_plan_contains_location_arguments() -> None:
    plan = DeterministicToolPlanner().build_plan(
        _turn("Show rain radar over Rome", layers=["rainviewer_precipitation_radar"]),
        "environmental_data",
    )
    assert plan.steps[0].arguments["capability_id"] == "rainviewer_precipitation_radar"
    assert plan.steps[0].arguments["arguments"]["location"] == "Rome"

###############################################################################
def test_provider_layer_selection_uses_map_preparation_tool() -> None:
    plan = DeterministicToolPlanner().build_plan(
        _turn(
            "Render the selected GIBS layer over Rome",
            layers=["gibs:MODIS_Terra_CorrectedReflectance_TrueColor"],
        ),
        "map_layers",
    )

    assert [step.tool_name for step in plan.steps] == ["prepare_geospatial_map"]
    assert plan.steps[0].arguments["layer_options"] == {
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

###############################################################################
def test_atomic_task_dependencies_and_bindings_reach_executable_plan() -> None:
    first_layer = "openmeteo_air_quality_forecast"
    second_layer = "openmeteo_weather_forecast"
    turn = _turn(
        "Compare the conditions using the first result",
        layers=[first_layer, second_layer],
    ).model_copy(
        update={
            "atomic_tasks": [
                {
                    "id": "fetch-air-quality",
                    "required_layers": [first_layer],
                    "output_refs": ["air-quality-result"],
                },
                {
                    "id": "compare-weather",
                    "required_layers": [second_layer],
                    "depends_on": ["fetch-air-quality"],
                    "input_refs": [
                        "fetch-air-quality:data.direct_result->arguments.reference"
                    ],
                },
            ]
        }
    )

    plan = DeterministicToolPlanner().build_plan(turn, "environmental_data")

    first, second = plan.steps
    assert first.parallel_group == "capability-fetch"
    assert second.depends_on == [first.step_id]
    assert second.input_bindings[0].target == "arguments.reference"
    assert second.input_bindings[0].source_step_id == first.step_id
    assert first.output_refs == ["air-quality-result"]

###############################################################################
def test_atomic_tasks_without_layer_refs_do_not_create_inferred_dependencies() -> None:
    turn = _turn(
        "Resolve the place and render it",
        layers=["openmeteo_air_quality_forecast", "openmeteo_weather_forecast"],
    ).model_copy(
        update={
            "atomic_tasks": [
                {"id": "first", "depends_on": [], "required_layers": []},
                {"id": "second", "depends_on": ["first"], "required_layers": []},
            ]
        }
    )

    plan = DeterministicToolPlanner().build_plan(turn, "environmental_data")

    assert [step.depends_on for step in plan.steps] == [[], []]

###############################################################################
def test_peer_targets_create_independent_capability_steps() -> None:
    turn = _turn(
        "Compare earthquakes in Paris and London",
        layers=["usgs_earthquakes"],
    ).model_copy(
        update={
            "location_signals": [
                LocationSignal(
                    signal_type="city",
                    raw_value="Paris",
                    normalized_value="Paris",
                    confidence=0.99,
                ),
                LocationSignal(
                    signal_type="city",
                    raw_value="London",
                    normalized_value="London",
                    confidence=0.99,
                ),
            ],
            "operations": ["compare"],
        }
    )
    canonical = RequestInterpreter().compile(
        request_id="peer-plan-1",
        turn=turn,
        resolved_locations={
            "paris": ResolvedLocation(
                label="Paris, France", latitude=48.8566, longitude=2.3522
            ),
            "london": ResolvedLocation(
                label="London, United Kingdom", latitude=51.5074, longitude=-0.1278
            ),
        },
    )

    plan = DeterministicToolPlanner().build_plan(
        turn,
        "environmental_data",
        canonical_request=canonical,
    )

    assert len(plan.steps) == 2
    assert [step.target_id for step in plan.steps] == ["target-1", "target-2"]
    assert [
        step.arguments["arguments"]["location"] for step in plan.steps
    ] == ["Paris, France", "London, United Kingdom"]

###############################################################################
def test_peer_targets_create_independent_provider_layer_steps() -> None:
    turn = _turn(
        "Compare the selected layer in Paris and London",
        layers=["gibs:MODIS_Terra_CorrectedReflectance_TrueColor"],
    ).model_copy(
        update={
            "location_signals": [
                LocationSignal(
                    signal_type="city",
                    raw_value="Paris",
                    normalized_value="Paris",
                    confidence=0.99,
                ),
                LocationSignal(
                    signal_type="city",
                    raw_value="London",
                    normalized_value="London",
                    confidence=0.99,
                ),
            ],
            "operations": ["compare"],
        }
    )
    canonical = RequestInterpreter().compile(
        request_id="peer-provider-plan-1",
        turn=turn,
        resolved_locations={
            "paris": ResolvedLocation(
                label="Paris, France", latitude=48.8566, longitude=2.3522
            ),
            "london": ResolvedLocation(
                label="London, United Kingdom", latitude=51.5074, longitude=-0.1278
            ),
        },
    )

    plan = DeterministicToolPlanner().build_plan(
        turn,
        "map_layers",
        canonical_request=canonical,
    )

    assert len(plan.steps) == 2
    assert [step.target_id for step in plan.steps] == ["target-1", "target-2"]
    assert all(
        step.tool_name == "prepare_geospatial_map" for step in plan.steps
    )
