from __future__ import annotations

from server.services.agent.parser_service import ParserService


###############################################################################
def test_parser_fallback_does_not_select_tools_or_action_execution_ids() -> None:
    extracted = ParserService._fallback_extraction("Show weather near Rome")

    payload = extracted.model_dump(mode="json")
    assert "tool_name" not in payload
    assert "tool_id" not in payload
    assert "execution_plan" not in payload
    assert "action_id" in payload


###############################################################################
def test_parser_can_extract_geospatial_entities_without_execution_steps() -> None:
    extracted = ParserService._fallback_extraction("Show a map of 41.9, 12.5")

    assert extracted.location_signals[0].signal_type == "coordinates"
    assert extracted.location_signals[0].latitude == 41.9
    assert extracted.location_signals[0].longitude == 12.5
    assert not hasattr(extracted, "tool_calls")

