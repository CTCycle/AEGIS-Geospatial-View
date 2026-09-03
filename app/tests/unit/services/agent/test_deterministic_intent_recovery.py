from __future__ import annotations

from server.services.agent.capability_resolver import CapabilityResolver
from server.services.agent.deterministic_intent_recovery import (
    DeterministicIntentRecoveryService,
)
from server.services.agent.turn_support import AgentTurnSupport
from server.services.geospatial.capability_registry import CapabilityRegistry
from server.services.geospatial.runtime_registry import RuntimeRegistry


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


def test_recovers_explicit_map_weather_request_as_map() -> None:
    result = _recover("Show humidity and pressure as a map around Sanremo.")

    assert result is not None
    assert result.task_class == "map_search"
    assert result.presentation_mode == "both"
    assert result.expected_frontend_update == "map_session"


def test_recovers_coordinate_map_and_combined_weather_request() -> None:
    result = _recover("Display weather and air quality at 43.817, 7.777.")

    assert result is not None
    assert result.location_signals[0].signal_type == "coordinates"
    assert result.location_signals[0].latitude == 43.817
    assert result.location_signals[0].longitude == 7.777
    assert result.requested_concepts == ["weather", "air quality"]


def test_does_not_recover_vague_or_ambiguous_requests() -> None:
    assert _recover("What can you do?") is None
    assert _recover("Show humidity in Rome and Milan.") is None
    assert _recover("Show humidity around there.") is None


def test_only_provider_timeouts_are_recoverable() -> None:
    result = DeterministicIntentRecoveryService.recover_explicit_request(
        user_message="Show humidity in Sanremo.",
        memory_snapshot={},
        conversation_messages=[],
        provider_error={"code": "auth_required", "category": "provider_api"},
    )

    assert result is None
