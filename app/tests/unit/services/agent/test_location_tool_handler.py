from __future__ import annotations

import pytest

from server.domain.agent.capability_route import AgentPhase, AgentState
from server.services.agent.location_resolver import LocationResolver
from server.services.agent.tool_definitions import ResolveLocationInput
from server.services.agent.tool_handlers.location import LocationToolHandler


###############################################################################
@pytest.mark.asyncio
async def test_coordinate_query_is_resolved_without_geocoder_egress() -> None:
    state = AgentState(
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
