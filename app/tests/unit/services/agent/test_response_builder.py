from __future__ import annotations

from server.domain.agent.decision import ResolvedLocation
from server.contracts.chat import ChatOperationResult
from server.contracts.geospatial import (
    MapSession,
    OverlayCollectionState,
    ViewportPolicy,
)
from server.services.agent.response_builder import AgentResponseBuilder


###############################################################################
def test_build_final_decision_maps_map_sessions_to_map_search_state() -> None:
    decision = AgentResponseBuilder.build_final_decision(
        action_id="map_search",
        operation=ChatOperationResult(
            kind="map_session",
            status="success",
            message="Map ready.",
        ),
        trace_steps=["verified"],
    )

    assert decision.plan.state == "map_search"
    assert decision.plan.mode == "map"


###############################################################################
def test_build_final_decision_maps_clarification_and_rejection_to_non_map_states() -> (
    None
):
    clarification = AgentResponseBuilder.build_final_decision(
        action_id="map_search",
        operation=ChatOperationResult(
            kind="clarification",
            status="partial",
            message="Need a location.",
        ),
        trace_steps=["clarify"],
    )
    rejection = AgentResponseBuilder.build_final_decision(
        action_id="map_search",
        operation=ChatOperationResult(
            kind="rejection",
            status="failed",
            message="Not allowed.",
        ),
        trace_steps=["reject"],
    )

    assert clarification.plan.state == "clarify"
    assert clarification.plan.mode is None
    assert rejection.plan.state == "reject"
    assert rejection.plan.mode is None


###############################################################################
def test_build_final_decision_maps_direct_answers_to_direct_text() -> None:
    decision = AgentResponseBuilder.build_final_decision(
        action_id="get_weather_forecast",
        operation=ChatOperationResult(
            kind="direct_answer",
            status="success",
            message="Forecast ready.",
            direct_result={"tool": "get_weather_forecast"},
        ),
        trace_steps=["direct"],
    )

    assert decision.plan.state == "direct_tool"
    assert decision.plan.mode == "direct_text"


###############################################################################
def test_map_response_preserves_and_renders_companion_direct_result() -> None:
    map_session = MapSession(
        session_id="map-weather",
        resolved_location=ResolvedLocation(
            label="Rome", latitude=41.9, longitude=12.5
        ),
        basemap_id="osm_default",
        viewport=ViewportPolicy(
            center_latitude=41.9, center_longitude=12.5, radius_m=18000.0
        ),
        overlay_collection=OverlayCollectionState(),
    )
    direct_result = {
        "tool_id": "get_weather_forecast",
        "location": "Rome",
        "result": {
            "current": {
                "time": "2026-09-01T09:00",
                "temperature_2m": 23.4,
                "precipitation": 0.0,
            }
        },
    }

    message = AgentResponseBuilder.build_verified_assistant_message(
        "fallback",
        map_session=map_session,
        direct_result=direct_result,
        tool_payload=None,
    )
    operation = AgentResponseBuilder.build_verified_operation_result(
        assistant_message=message,
        map_session=map_session,
        direct_result=direct_result,
        tool_payload=None,
        user_text="What is the weather?",
        is_capability_question=False,
    )

    assert "Map ready for Rome" in message
    assert "temperature 23.4 C" in message
    assert operation.kind == "map_session"
    assert operation.direct_result == direct_result
