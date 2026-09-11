from __future__ import annotations

from server.services.agent.capability_resolver import CapabilityResolver
from server.contracts.extraction import (
    ConversationContextSnapshot,
    NormalizedAction,
    TurnParseResult,
)
from server.services.agent.deterministic_intent_recovery import (
    DeterministicIntentRecoveryService,
)
from server.services.agent.turn_support import AgentTurnSupport
from server.services.geospatial.capability_registry import CapabilityRegistry
from server.services.geospatial.runtime_registry import RuntimeRegistry

###############################################################################
def _recover(message: str):
    return DeterministicIntentRecoveryService.recover_explicit_request(
        user_message=message,
        memory_snapshot={},
        conversation_messages=[],
        provider_error={
            "code": "provider_timeout",
            "category": "provider_api",
            "provider": "test",
            "model": "test-model",
        },
    )

###############################################################################
def test_recovers_direct_humidity_request_as_catalog_backed_value_lookup() -> None:
    result = _recover("Show the current humidity level in Sanremo.")

    assert result is not None
    assert result.task_class == "direct_query"
    assert result.normalized_action.action_id == "data_layer_query"
    assert result.location_signals[0].normalized_value == "Sanremo"
    assert result.requested_concepts == ["humidity"]
    assert result.presentation_mode == "text"
    assert result.expected_frontend_update == "chat"
    assert result.provider_error == {
        "code": "provider_timeout",
        "category": "provider_api",
        "provider": "test",
        "model": "test-model",
        "recovered": True,
        "recovery": "explicit_catalog_request",
    }
    assert not AgentTurnSupport.has_parser_runtime_failure(result)

    resolved = CapabilityResolver(
        capability_registry=CapabilityRegistry(),
        runtime_registry=RuntimeRegistry(),
    ).resolve(result)
    assert resolved.requested_layers == ["get_weather_forecast"]

###############################################################################
def test_recovers_explicit_map_weather_request_as_map() -> None:
    result = _recover("Show humidity and pressure as a map around Sanremo.")

    assert result is not None
    assert result.task_class == "map_search"
    assert result.presentation_mode == "both"
    assert result.expected_frontend_update == "map_session"

###############################################################################
def test_preserves_recent_temporal_qualifier_during_timeout_recovery() -> None:
    result = _recover("Show recent weather in Sanremo on the map.")

    assert result is not None
    assert result.temporal_signal.raw_text == "recent"
    assert result.temporal_signal.mode == "current"
    assert result.requested_concepts == ["weather"]

###############################################################################
def test_recovers_explicit_request_after_structured_payload_failure() -> None:
    result = DeterministicIntentRecoveryService.recover_explicit_request(
        user_message="Show weather in Sanremo on the map.",
        memory_snapshot={},
        conversation_messages=[],
        provider_error={
            "code": "structured_invalid_payload",
            "category": "response_parsing",
        },
    )

    assert result is not None
    assert result.task_class == "map_search"
    assert result.location_signals[0].normalized_value == "Sanremo"
    assert result.provider_error["recovered"] is True
    assert result.provider_error["recovery"] == "explicit_catalog_request"

###############################################################################
def test_recovers_coordinate_map_and_combined_weather_request() -> None:
    result = _recover("Display weather and air quality at 43.817, 7.777.")

    assert result is not None
    assert result.location_signals[0].signal_type == "coordinates"
    assert result.location_signals[0].latitude == 43.817
    assert result.location_signals[0].longitude == 7.777
    assert result.requested_concepts == ["weather", "air quality"]

###############################################################################
def test_recovers_catalog_backed_compound_request_after_application_deadline() -> None:
    result = DeterministicIntentRecoveryService.recover_explicit_request(
        user_message=(
            "Show weather and earthquakes within 100 km of Denver, United States "
            "on the map."
        ),
        memory_snapshot={},
        conversation_messages=[],
        provider_error={"code": "application_deadline_exceeded"},
        capability_catalog=[
            {
                "id": "weather-layer",
                "name": "Weather observations",
                "capabilities": ["weather"],
                "metadata": {"keywords": ["forecast"]},
            },
            {
                "id": "seismic-layer",
                "name": "Earthquake observations",
                "capabilities": ["earthquake"],
                "metadata": {"keywords": ["seismic"]},
            },
        ],
    )

    assert result is not None
    assert result.requested_concepts == ["weather", "earthquake"]
    assert result.radius_m == 100_000
    assert result.presentation_mode == "both"
    assert result.provider_error["recovered"] is True

###############################################################################
def test_recovers_contextual_location_request_for_non_vector_capability() -> None:
    result = DeterministicIntentRecoveryService.recover_explicit_request(
        user_message="Map current measurements around Example City.",
        memory_snapshot={},
        conversation_messages=[],
        provider_error={"code": "provider_timeout"},
        capability_catalog=[
            {
                "id": "point-measurements",
                "name": "Point Measurements",
                "capabilities": ["measurement"],
                "type": "direct-tool",
                "capabilityKind": "analysis-tool",
                "metadata": {
                    "supports_map": True,
                    "geometry_type": "not-applicable",
                    "queryable": False,
                    "vectorizable": False,
                },
            }
        ],
    )

    assert result is not None
    assert result.location_signals[0].normalized_value == "Example City"
    assert result.requested_concepts == ["measurement"]
    assert result.radius_m is None
    assert result.presentation_mode == "both"

###############################################################################
def test_recovers_contextual_extent_when_capability_declares_bbox_support() -> None:
    result = DeterministicIntentRecoveryService.recover_explicit_request(
        user_message="Show an observation record around Example City on the map.",
        memory_snapshot={},
        conversation_messages=[],
        provider_error={"code": "provider_timeout"},
        capability_catalog=[
            {
                "id": "bounded-observations",
                "name": "Bounded Observation Data",
                "capabilities": ["observation", "record"],
                "type": "vector-overlay",
                "capabilityKind": "vector-overlay",
                "metadata": {
                    "supports_map": True,
                    "geometry_type": "Point",
                    "queryable": True,
                    "vectorizable": True,
                },
                "executionContract": {
                    "supported_scope_kinds": ["bbox", "radius"]
                },
            }
        ],
    )

    assert result is not None
    assert result.requested_concepts == ["observation", "record"]
    assert result.radius_m is None

###############################################################################
def test_keeps_distance_based_vector_search_ambiguous_without_radius() -> None:
    result = DeterministicIntentRecoveryService.recover_explicit_request(
        user_message="Show observation records near Example City on the map.",
        memory_snapshot={},
        conversation_messages=[],
        provider_error={"code": "provider_timeout"},
        capability_catalog=[
            {
                "id": "bounded-observations",
                "name": "Bounded Observation Records",
                "capabilities": ["observations", "records"],
                "type": "vector-overlay",
                "capabilityKind": "vector-overlay",
                "metadata": {
                    "supports_map": True,
                    "geometry_type": "Point",
                    "queryable": True,
                    "vectorizable": True,
                },
                "executionContract": {
                    "supported_scope_kinds": ["bbox", "radius"]
                },
            }
        ],
    )

    assert result is None

###############################################################################
def test_recovers_clarification_answer_against_pending_request_contract() -> None:
    result = DeterministicIntentRecoveryService.recover_explicit_request(
        user_message="Use the last 2 hours.",
        memory_snapshot={},
        conversation_messages=[
            {
                "role": "user",
                "content": "Show recent rain radar over Denver, Colorado, United States on the map.",
            },
            {
                "role": "assistant",
                "content": "Please specify the time window to use for recent data.",
            },
        ],
        provider_error={"code": "application_deadline_exceeded"},
        capability_catalog=[
            {
                "id": "rain-radar",
                "name": "Recent precipitation radar",
                "capabilities": ["radar", "precipitation"],
                "metadata": {"keywords": ["rain", "recent radar history"]},
            }
        ],
        latest_contract={
            "user_text": "Show recent rain radar over Denver, Colorado, United States on the map.",
            "task_class": "map_search",
            "normalized_action": {
                "action_id": "show_overlay",
                "action_label": "Show a geospatial overlay",
                "task_tags": ["map", "overlay"],
                "action_tags": ["show"],
                "requested_visualizations": ["map"],
                "requires_location": True,
            },
            "temporal_signal": {
                "mode": "current",
                "raw_text": "recent",
                "start_time_iso": None,
                "end_time_iso": None,
            },
            "operations": ["show_overlay"],
            "presentation_requirements": {"map": True},
            "requested_layers": ["rainviewer_radar"],
            "overlay_commands": [
                {
                    "action": "add",
                    "selector": {"concepts": ["radar"]},
                    "scope": {"kind": "location", "label": "Denver"},
                }
            ],
            "required_data_sources": ["rainviewer"],
            "required_tool_category": "raster",
            "tools_needed": True,
            "direct_response_sufficient": False,
            "expected_frontend_update": "map_session",
            "ambiguities": ["recent_requires_time_window"],
            "clarification_plan": {
                "blocking_fields": ["time_window"],
            },
        },
    )

    assert result is not None
    assert result.task_class == "map_search"
    assert result.location_signals[0].normalized_value == (
        "Denver, Colorado, United States"
    )
    assert result.requested_concepts == ["precipitation", "rain", "radar"]
    assert result.temporal_signal.raw_text == "last 2 hours"
    assert result.temporal_signal.mode == "current"
    assert result.normalized_action.action_id == "show_overlay"
    assert result.operations == ["show_overlay"]
    assert result.requested_layers == ["rainviewer_radar"]
    assert result.overlay_commands[0].selector.concepts == ["radar"]
    assert result.required_data_sources == ["rainviewer"]
    assert result.expected_frontend_update == "map_session"
    assert result.ambiguities == []
    assert result.clarification_plan is None
    assert result.provider_error["recovery"] == "clarification_follow_up"

###############################################################################
def test_continues_valid_parser_answer_against_pending_location_contract() -> None:
    current_turn = TurnParseResult(
        user_text="Bologna, Italy.",
        conversation_context=ConversationContextSnapshot(),
        task_class="map_search",
        normalized_action=NormalizedAction(
            action_id="location_render",
            action_label="Show map",
            requires_location=True,
        ),
    )

    result = DeterministicIntentRecoveryService.continue_pending_request(
        turn=current_turn,
        user_message="Bologna, Italy.",
        latest_contract={
            "user_text": "Map GBIF species occurrences within 20 km.",
            "task_class": "map_search",
            "normalized_action": {
                "action_id": "data_layer_query",
                "action_label": "Map data",
                "requires_location": True,
            },
            "requested_layers": ["gbif_species_occurrences"],
            "required_data_sources": ["gbif_species_occurrences"],
            "tools_needed": True,
            "expected_frontend_update": "map_session",
            "presentation_mode": "map",
            "clarification_plan": {
                "blocking_fields": ["location"],
                "question": "Which location should I use?",
            },
        },
    )

    assert result is not None
    assert result.relationship == "clarification"
    assert result.location_signals[0].normalized_value == "Bologna, Italy"
    assert result.requested_layers == ["gbif_species_occurrences"]
    assert result.required_data_sources == ["gbif_species_occurrences"]
    assert result.expected_frontend_update == "map_session"
    assert result.clarification_plan is None

###############################################################################
def test_continuation_preserves_parent_temporal_mode_for_window_answer() -> None:
    current_turn = TurnParseResult(
        user_text="Use the last 2 hours.",
        conversation_context=ConversationContextSnapshot(),
        task_class="map_search",
        normalized_action=NormalizedAction(
            action_id="data_layer_query",
            action_label="Query map data",
            requires_location=True,
        ),
        temporal_signal={
            "mode": "historical",
            "raw_text": "last 2 hours",
            "granularity": "hour",
        },
    )

    result = DeterministicIntentRecoveryService.continue_pending_request(
        turn=current_turn,
        user_message=current_turn.user_text,
        latest_contract={
            "user_text": "Show recent precipitation over Example City on the map.",
            "task_class": "map_search",
            "normalized_action": {
                "action_id": "data_layer_query",
                "action_label": "Query map data",
                "requires_location": True,
            },
            "temporal_signal": {
                "mode": "current",
                "raw_text": "recent",
            },
            "requested_layers": ["rain-layer"],
            "required_data_sources": ["rain-layer"],
            "tools_needed": True,
            "expected_frontend_update": "map_session",
            "clarification_plan": {
                "blocking_fields": ["time_window"],
            },
        },
    )

    assert result is not None
    assert result.temporal_signal.mode == "current"
    assert result.temporal_signal.raw_text == "last 2 hours"
    assert result.clarification_plan is None


###############################################################################
def test_continuation_recognizes_singular_window_and_preserves_parent_mode() -> None:
    current_turn = TurnParseResult(
        user_text="Use the last hour.",
        conversation_context=ConversationContextSnapshot(),
        task_class="map_search",
        normalized_action=NormalizedAction(
            action_id="data_layer_query",
            action_label="Query map data",
            requires_location=True,
        ),
        temporal_signal={
            "mode": "historical",
            "raw_text": "the last hour",
            "granularity": "hour",
        },
    )

    result = DeterministicIntentRecoveryService.continue_pending_request(
        turn=current_turn,
        user_message=current_turn.user_text,
        latest_contract={
            "user_text": "Show recent precipitation over Example City on the map.",
            "task_class": "map_search",
            "normalized_action": {
                "action_id": "data_layer_query",
                "action_label": "Query map data",
                "requires_location": True,
            },
            "temporal_signal": {
                "mode": "current",
                "raw_text": "recent",
            },
            "requested_layers": ["rain-layer"],
            "required_data_sources": ["rain-layer"],
            "tools_needed": True,
            "expected_frontend_update": "map_session",
            "clarification_plan": {
                "blocking_fields": ["time_window"],
            },
        },
    )

    assert result is not None
    assert result.temporal_signal.mode == "current"
    assert result.temporal_signal.raw_text == "last hour"
    assert result.clarification_plan is None

###############################################################################
def test_continuation_merges_current_quantitative_answer_with_parent_contract() -> None:
    current_turn = TurnParseResult(
        user_text="Limit it to 25 results above magnitude 4.",
        conversation_context=ConversationContextSnapshot(),
        task_class="direct_query",
        normalized_action=NormalizedAction(
            action_id="data_layer_query",
            action_label="Query data",
            requires_location=False,
        ),
        result_limit=25,
        filters={"magnitude_threshold": 4.0},
    )

    result = DeterministicIntentRecoveryService.continue_pending_request(
        turn=current_turn,
        user_message=current_turn.user_text,
        latest_contract={
            "user_text": "Show earthquakes in Italy.",
            "task_class": "direct_query",
            "normalized_action": {
                "action_id": "data_layer_query",
                "action_label": "Query data",
                "requires_location": True,
            },
            "requested_layers": ["earthquakes"],
            "required_data_sources": ["earthquakes"],
            "filters": {"region": "Italy", "top_n": 10},
            "tools_needed": True,
            "expected_frontend_update": "chat",
            "clarification_plan": {
                "blocking_fields": ["result_limit", "magnitude_threshold"],
            },
        },
    )

    assert result is not None
    assert result.filters == {
        "region": "Italy",
        "top_n": 10,
        "magnitude_threshold": 4.0,
    }
    assert result.result_limit == 25
    assert result.requested_layers == ["earthquakes"]

###############################################################################
def test_does_not_recover_vague_or_ambiguous_requests() -> None:
    assert _recover("What can you do?") is None
    assert _recover("Show humidity in Rome and Milan.") is None
    assert _recover("Show humidity around there.") is None

###############################################################################
def test_only_provider_timeouts_are_recoverable() -> None:
    result = DeterministicIntentRecoveryService.recover_explicit_request(
        user_message="Show humidity in Sanremo.",
        memory_snapshot={},
        conversation_messages=[],
        provider_error={"code": "auth_required", "category": "provider_api"},
    )

    assert result is None
