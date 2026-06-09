from __future__ import annotations

from server.domain.chat import ChatOperationResult
from server.services.agent.response_builder import AgentResponseBuilder


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


def test_build_final_decision_maps_clarification_and_rejection_to_non_map_states() -> None:
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
