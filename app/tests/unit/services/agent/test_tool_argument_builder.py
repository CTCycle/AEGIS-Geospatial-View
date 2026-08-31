from __future__ import annotations

from server.contracts.extraction import (
    ConversationContextSnapshot,
    LocationSignal,
    NormalizedAction,
    TemporalSignal,
    TurnParseResult,
)
from server.services.agent.tool_argument_builder import ToolArgumentBuilder


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
