from __future__ import annotations

import pytest

from server.domain.agent.capability_route import AgentPhase, AgentRunState
from server.services.agent.location_resolver import LocationResolver
from server.services.agent.tool_definitions import ResolveLocationInput
from server.services.agent.tool_handlers.location import LocationToolHandler
from server.domain.agent.decision import ClarificationRequest


###############################################################################
@pytest.mark.asyncio
async def test_coordinate_query_is_resolved_without_geocoder_egress() -> None:
    state = AgentRunState(
        request_id="request-1",
        conversation_id="conversation-1",
        phase=AgentPhase.BUILD_TOOL_CONTEXT,
        user_message="Show 46.0037, 8.9511.",
    )

    result = await LocationToolHandler(resolver=LocationResolver()).resolve(
        ResolveLocationInput(query="46.0037, 8.9511"),
        state,
    )

    assert result.status == "success"
    location = state.location_refs["46.0037, 8.9511"]
    assert location.latitude == 46.0037
    assert location.longitude == 8.9511


###############################################################################
@pytest.mark.asyncio
async def test_ambiguous_location_is_a_typed_semantic_outcome() -> None:
    class AmbiguousResolver(LocationResolver):
        async def resolve_location_signals(self, _signals, _memory):  # noqa: ANN001
            return ClarificationRequest(
                question="Which Springfield do you mean?",
                reason="Multiple candidates matched.",
                missing_fields=["location"],
            )

    result = await LocationToolHandler(resolver=AmbiguousResolver()).resolve(
        ResolveLocationInput(query="Springfield"),
        AgentRunState(
            request_id="request-1",
            conversation_id="conversation-1",
            phase=AgentPhase.BUILD_TOOL_CONTEXT,
            user_message="Show Springfield.",
        ),
    )

    assert result.status == "failed"
    assert result.semantic_outcome == "ambiguous"
    assert result.data == {
        "resolution_status": "ambiguous",
        "question": "Which Springfield do you mean?",
        "reason": "Multiple candidates matched.",
        "missing_fields": ["location"],
    }
    assert result.error is not None
    assert result.error.recovery == "request_user_input"
