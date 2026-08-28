from __future__ import annotations

from server.services.agent.parser_service import ParserService

###############################################################################
def _failure():  # noqa: ANN202
    return ParserService.build_parser_failure_turn_result(
        user_message="Show weather near Rome",
        memory_snapshot={},
        conversation_messages=[],
        provider_error={
            "code": "provider_request_failed",
            "category": "provider_api",
            "provider": "opencode-go",
            "model": "deepseek-v4-flash",
            "stage": "structured_output",
        },
    )

###############################################################################
def test_parser_failure_contract_is_non_executable_and_diagnostic() -> None:
    result = _failure()

    assert result.task_class == "unclear"
    assert result.normalized_action.action_id == "unknown"
    assert result.location_signals == []
    assert result.requested_layers == []
    assert result.requested_basemap is None
    assert result.overlay_commands == []
    assert result.expected_frontend_update == "failure_diagnostic"
    assert result.failure_category == "provider_api"

###############################################################################
def test_structural_coordinate_extraction_is_independent_of_execution_planning() -> None:
    extracted = ParserService._extract_coordinate_signal("Show a map of 41.9, 12.5")

    assert extracted is not None
    assert extracted.signal_type == "coordinates"
    assert extracted.latitude == 41.9
    assert extracted.longitude == 12.5
