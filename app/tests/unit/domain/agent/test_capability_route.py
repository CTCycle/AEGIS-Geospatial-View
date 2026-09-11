from __future__ import annotations

import pytest
from pydantic import ValidationError

from server.domain.agent.capability_route import (
    AgentPhase,
    AgentState,
    CapabilityDomain,
    CapabilityRoute,
)


###############################################################################
def test_capability_route_is_bounded_and_strict() -> None:
    route = CapabilityRoute(
        primary_domain=CapabilityDomain.DATA_RETRIEVAL,
        secondary_domains=[CapabilityDomain.MAP_RENDERING],
        task_mode="execute",
        presentation="both",
        requires_location=True,
        capability_queries=["hospitals"],
    )

    assert route.primary_domain is CapabilityDomain.DATA_RETRIEVAL
    assert route.presentation == "both"

    with pytest.raises(ValidationError):
        CapabilityRoute(
            primary_domain="not-a-domain",
            task_mode="execute",
            presentation="text",
            requires_location=False,
        )

    with pytest.raises(ValidationError):
        CapabilityRoute(
            primary_domain="conversation",
            task_mode="execute",
            presentation="text",
            requires_location=False,
            unexpected=True,
        )


###############################################################################
def test_agent_state_tracks_native_loop_counters() -> None:
    state = AgentState(
        request_id="req-1",
        conversation_id="conversation-1",
        phase=AgentPhase.ROUTE_REQUEST,
        user_message="Find Zurich.",
    )

    assert state.phase is AgentPhase.ROUTE_REQUEST
    assert state.tool_results == []
    with pytest.raises(ValidationError):
        AgentState(
            request_id="req-1",
            conversation_id="conversation-1",
            phase=AgentPhase.ROUTE_REQUEST,
            user_message="Find Zurich.",
            unexpected=True,
        )
