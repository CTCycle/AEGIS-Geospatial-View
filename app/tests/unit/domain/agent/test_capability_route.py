from __future__ import annotations

import pytest
from pydantic import ValidationError

from server.domain.agent.capability_route import (
    AgentPhase,
    AgentRunState,
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
    state = AgentRunState(
        request_id="req-1",
        conversation_id="conversation-1",
        phase=AgentPhase.ROUTE_REQUEST,
        user_message="Find Zurich.",
    )

    assert state.phase is AgentPhase.ROUTE_REQUEST
    assert state.tool_results == []
    with pytest.raises(ValidationError):
        AgentRunState(
            request_id="req-1",
            conversation_id="conversation-1",
            phase=AgentPhase.ROUTE_REQUEST,
            user_message="Find Zurich.",
            unexpected=True,
        )


###############################################################################
def test_agent_run_state_is_the_single_checkpointable_native_state() -> None:
    state = AgentRunState(
        request_id="req-1",
        run_id="run-1",
        run_version=3,
        conversation_revision=7,
        conversation_id="conversation-1",
        phase=AgentPhase.ROUTE_REQUEST,
        user_message="Find Zurich.",
    )

    restored = AgentRunState.from_checkpoint(state.checkpoint())

    assert restored.run_version == 3
    assert restored.conversation_revision == 7
    assert restored.request_id == state.request_id
