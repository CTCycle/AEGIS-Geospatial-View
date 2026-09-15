from __future__ import annotations

import asyncio
from typing import Any

from server.domain.agent.capability_route import AgentPhase, AgentRunState
from server.services.agent.tool_definitions import CapabilityDiscoveryInput
from server.services.agent.tool_handlers.catalog import CatalogToolHandler


###############################################################################
class _CapabilityRegistry:

    # -------------------------------------------------------------------------
    def shortlist(self, **_kwargs: Any) -> list[dict[str, Any]]:
        return [
            {"id": "first", "name": "First", "provider": "test"},
            {"id": "second", "name": "Second", "provider": "test"},
        ]

    # -------------------------------------------------------------------------
    def execution_contract(self, capability_id: str) -> dict[str, Any]:
        return {"capability_id": capability_id}


###############################################################################
class _RuntimeRegistry:

    # -------------------------------------------------------------------------
    def is_enabled(self, _capability_id: str) -> bool:
        return True

    # -------------------------------------------------------------------------
    def access_available(self, _capability_id: str) -> bool:
        return True


###############################################################################
def test_discovery_cursor_returns_a_stable_bounded_page() -> None:
    handler = CatalogToolHandler(
        capability_registry=_CapabilityRegistry(),  # type: ignore[arg-type]
        runtime_registry=_RuntimeRegistry(),  # type: ignore[arg-type]
    )
    state = AgentRunState(
        request_id="request-1",
        conversation_id="conversation-1",
        phase=AgentPhase.BUILD_TOOL_CONTEXT,
        user_message="find capabilities",
    )

    result = asyncio.run(
        handler.discover(
            CapabilityDiscoveryInput(cursor="1", limit=1),
            state,
        )
    )

    assert result.status == "success"
    assert result.data == {
        "capabilities": [
            {
                "id": "second",
                "name": "Second",
                "description": "",
                "provider": "test",
                "kind": "unknown",
                "supports_map": True,
                "execution_contract": {"capability_id": "second"},
            }
        ],
        "provider_id": None,
        "next_cursor": None,
        "total": 2,
    }
