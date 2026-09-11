from __future__ import annotations

from server.contracts.extraction import (
    ConversationContextSnapshot,
    LocationSignal,
    NormalizedAction,
    TemporalSignal,
    TurnParseResult,
    ViewportIntent,
)
from server.domain.agent.decision import ResolvedLocation
from server.domain.agent.interpretation import (
    CanonicalRequestInterpretation,
    CanonicalSpatialConstraint,
    CanonicalTarget,
)
from server.services.agent.request_interpreter import RequestInterpreter
from server.services.agent.tool_argument_builder import ToolArgumentBuilder
from server.services.geospatial.capability_registry import CapabilityRegistry

###############################################################################
def _turn(temporal: TemporalSignal) -> TurnParseResult:
    return TurnParseResult(
        user_text="Show the weather there",
        conversation_context=ConversationContextSnapshot(),
        task_class="direct_query",
        location_signals=[
            LocationSignal(
                signal_type="city",
                raw_value="Zurich",
                normalized_value="Zurich",
                latitude=47.3769,
                longitude=8.5417,
                confidence=0.99,
            )
        ],
        normalized_action=NormalizedAction(
            action_id="data_layer_query",
            action_label="Weather",
            requires_location=True,
        ),
        temporal_signal=temporal,
    )

###############################################################################
def test_current_mode_does_not_forward_non_temporal_parser_text() -> None:
    arguments = ToolArgumentBuilder.build_temporal_arguments(
        _turn(TemporalSignal(mode="current", raw_text="show the weather there"))
    )

    assert arguments == {"temporal_mode": "current"}

###############################################################################
def test_forecast_mode_preserves_temporal_phrase_for_selection() -> None:
    arguments = ToolArgumentBuilder.build_temporal_arguments(
        _turn(TemporalSignal(mode="forecast", raw_text="tomorrow"))
    )

    assert arguments == {"temporal_mode": "forecast", "time": "tomorrow"}

###############################################################################
def test_explicit_correction_location_precedes_remembered_bbox() -> None:
    turn = _turn(
        TemporalSignal(mode="current"),
    )
    turn = turn.model_copy(
        update={
            "user_text": "Actually use Zurich instead.",
            "location_signals": [
                turn.location_signals[0].model_copy(
                    update={"raw_value": "Zurich", "normalized_value": "Zurich"}
                )
            ],
        }
    )

    arguments = ToolArgumentBuilder().build_capability_arguments(
        "openmeteo_air_quality_forecast",
        turn,
        {"bbox": [8.9, 45.9, 9.0, 46.1]},
    )

    assert arguments["location"] == "Zurich"
    assert arguments["latitude"] == 47.3769
    assert arguments["longitude"] == 8.5417
    assert "bbox" not in arguments

###############################################################################
def test_poi_constraints_reach_the_direct_tool_arguments() -> None:
    turn = _turn(TemporalSignal(mode="current")).model_copy(
        update={
            "normalized_action": NormalizedAction(
                action_id="geospatial_data_retrieval",
                action_label="Nearby hospitals",
                requires_location=True,
            ),
            "poi_categories": ["hospitals"],
            "radius_m": 1500.0,
            "result_limit": 25,
        }
    )

    arguments = ToolArgumentBuilder().build_capability_arguments(
        "get_nearby_poi", turn, {}
    )

    assert arguments["poi_categories"] == ["hospitals"]
    assert arguments["categories"] == ["hospitals"]
    assert arguments["radius_m"] == 1500.0
    assert arguments["limit"] == 25

###############################################################################
def test_canonical_radius_does_not_fall_back_to_geocoder_bbox() -> None:
    turn = _turn(TemporalSignal(mode="current")).model_copy(
        update={
            "user_text": "Show earthquakes within 5 km of Zurich",
            "radius_m": 5000.0,
            "requested_layers": ["usgs_earthquakes"],
        }
    )
    location = ResolvedLocation(
        label="Zurich, Switzerland",
        latitude=47.3769,
        longitude=8.5417,
        location_type="city",
        bbox=[8.3, 47.2, 8.7, 47.6],
    )
    canonical = RequestInterpreter().compile(
        request_id="radius-1",
        turn=turn,
        resolved_location=location,
    )

    arguments = ToolArgumentBuilder().build_capability_arguments(
        "usgs_earthquakes",
        turn,
        {"bbox": [0.0, 0.0, 1.0, 1.0]},
        resolved_location=location,
        canonical_request=canonical,
    )

    assert arguments["latitude"] == 47.3769
    assert arguments["longitude"] == 8.5417
    assert arguments["radius_m"] == 5000.0
    assert "bbox" not in arguments


###############################################################################
def test_point_metadata_capability_uses_target_point_in_area_search() -> None:
    turn = _turn(TemporalSignal(mode="current")).model_copy(
        update={
            "task_class": "map_search",
            "user_text": "Show weather within 100 km of Zurich",
            "radius_m": 100_000.0,
            "requested_layers": ["openmeteo_weather_forecast"],
        }
    )
    location = ResolvedLocation(
        label="Zurich, Switzerland",
        latitude=47.3769,
        longitude=8.5417,
        location_type="city",
    )
    canonical = CanonicalRequestInterpretation(
        request_id="point-sample-area-1",
        primary_intent="data_layer_query",
        targets=[
            CanonicalTarget(
                target_id="target-1",
                original_text="Zurich",
                entity_kind="city",
                resolved_location=location,
                resolution_status="resolved",
            )
        ],
        spatial_constraints=[
            CanonicalSpatialConstraint(
                relationship="within_distance",
                target_id="target-1",
                analysis_scope="radius",
                distance_m=100_000.0,
                provenance="explicit",
            )
        ],
    )

    arguments = ToolArgumentBuilder(
        capability_registry=CapabilityRegistry()
    ).build_capability_arguments(
        "openmeteo_weather_forecast",
        turn,
        {},
        resolved_location=location,
        canonical_request=canonical,
        target_id="target-1",
    )

    assert arguments["latitude"] == location.latitude
    assert arguments["longitude"] == location.longitude
    assert "radius_m" not in arguments
    assert "bbox" not in arguments

###############################################################################
def test_canonical_iso_temporal_window_is_authoritative() -> None:
    turn = _turn(
        TemporalSignal(
            mode="historical",
            raw_text="last week",
            start_time_iso="2026-08-24T00:00:00+00:00",
            end_time_iso="2026-08-31T00:00:00+00:00",
        )
    )
    arguments = ToolArgumentBuilder.build_temporal_arguments(
        turn,
        RequestInterpreter().compile(
            request_id="time-1",
            turn=turn,
            resolved_location=ResolvedLocation(
                label="Zurich",
                latitude=47.3769,
                longitude=8.5417,
            ),
        ),
    )

    assert arguments["start_time_iso"] == "2026-08-24T00:00:00+00:00"
    assert arguments["end_time_iso"] == "2026-08-31T00:00:00+00:00"
    assert "time" not in arguments

###############################################################################
def test_unresolved_canonical_target_does_not_fall_back_to_raw_or_memory() -> None:
    turn = _turn(TemporalSignal(mode="current")).model_copy(
        update={"user_text": "Show weather in an unresolved place"}
    )
    canonical = CanonicalRequestInterpretation(
        request_id="unresolved-1",
        primary_intent="data_layer_query",
        targets=[
            CanonicalTarget(
                target_id="target-1",
                original_text="an unresolved place",
                entity_kind="city",
            )
        ],
    )

    arguments = ToolArgumentBuilder().build_capability_arguments(
        "openmeteo_air_quality_forecast",
        turn,
        {
            "active_location": {
                "label": "Paris",
                "latitude": 48.8566,
                "longitude": 2.3522,
            }
        },
        canonical_request=canonical,
        target_id="target-1",
    )

    assert arguments == {}

###############################################################################
def test_canonical_viewport_radius_hint_is_not_an_analysis_radius() -> None:
    turn = _turn(TemporalSignal(mode="current")).model_copy(
        update={
            "viewport_intent": ViewportIntent(
                scope="city",
                radius_hint_m=12_000.0,
            )
        }
    )
    location = ResolvedLocation(
        label="Zurich",
        latitude=47.3769,
        longitude=8.5417,
        location_type="city",
    )
    canonical = RequestInterpreter().compile(
        request_id="viewport-radius-1",
        turn=turn,
        resolved_location=location,
    )

    arguments = ToolArgumentBuilder().build_capability_arguments(
        "usgs_earthquakes",
        turn,
        {},
        resolved_location=location,
        canonical_request=canonical,
    )

    assert "radius_m" not in arguments

###############################################################################
def test_canonical_point_scope_does_not_become_geocoder_bbox() -> None:
    location = ResolvedLocation(
        label="Zurich",
        latitude=47.3769,
        longitude=8.5417,
        location_type="city",
        bbox=[8.3, 47.2, 8.7, 47.6],
    )
    canonical = CanonicalRequestInterpretation(
        request_id="point-scope-1",
        primary_intent="inspect",
        targets=[
            CanonicalTarget(
                target_id="target-1",
                original_text="Zurich",
                entity_kind="city",
                resolved_location=location,
                resolution_status="resolved",
            )
        ],
        spatial_constraints=[
            CanonicalSpatialConstraint(
                relationship="at",
                target_id="target-1",
                analysis_scope="point",
                provenance="explicit",
            )
        ],
    )

    arguments = ToolArgumentBuilder().build_bbox_arguments(
        _turn(TemporalSignal(mode="current")),
        {},
        canonical_request=canonical,
        target_id="target-1",
    )

    assert arguments["latitude"] == location.latitude
    assert arguments["longitude"] == location.longitude
    assert "bbox" not in arguments

###############################################################################
def test_canonical_viewport_scope_does_not_use_target_bbox_as_analysis_area() -> None:
    location = ResolvedLocation(
        label="Zurich",
        latitude=47.3769,
        longitude=8.5417,
        location_type="city",
        bbox=[8.3, 47.2, 8.7, 47.6],
    )
    canonical = CanonicalRequestInterpretation(
        request_id="viewport-scope-1",
        primary_intent="visible_area",
        targets=[
            CanonicalTarget(
                target_id="target-1",
                original_text="Zurich",
                entity_kind="city",
                resolved_location=location,
                resolution_status="resolved",
            )
        ],
        spatial_constraints=[
            CanonicalSpatialConstraint(
                relationship="visible_area",
                target_id="target-1",
                analysis_scope="viewport",
                provenance="viewport",
            )
        ],
    )

    arguments = ToolArgumentBuilder().build_bbox_arguments(
        _turn(TemporalSignal(mode="current")),
        {},
        canonical_request=canonical,
        target_id="target-1",
    )

    assert arguments == {}
