from __future__ import annotations

import asyncio
from typing import Any

from server.domain.agent.capability_domains import CapabilityDomain
from server.domain.agent.capability_route import CapabilityRoute
from server.domain.agent.capability_route import AgentPhase, AgentRunState
from server.services.agent.tool_definitions import CapabilityDiscoveryInput
from server.services.agent.tool_handlers.catalog import CatalogToolHandler

###############################################################################
class _CapabilityRegistry:

    def __init__(self) -> None:
        self.last_shortlist_kwargs: dict[str, Any] = {}
        self.items = [
            {"id": "first", "name": "First", "provider": "test"},
            {"id": "second", "name": "Second", "provider": "test"},
        ]

    # -------------------------------------------------------------------------
    def shortlist(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.last_shortlist_kwargs = kwargs
        return self.items

    # -------------------------------------------------------------------------
    def execution_contract(self, capability_id: str) -> dict[str, Any]:
        return {"capability_id": capability_id, "render_support": "vector"}

###############################################################################
class _RuntimeRegistry:

    # -------------------------------------------------------------------------
    def is_enabled(self, _capability_id: str) -> bool:
        return True

    # -------------------------------------------------------------------------
    def access_available(self, _capability_id: str) -> bool:
        return True

    # -------------------------------------------------------------------------
    def supports_mode(self, _capability_id: str, _mode: str) -> bool:
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
                    "summary": "",
                    "provider": "test",
                    "operations": [],
                    "render_support": "vector",
                }
        ],
        "provider_id": None,
        "next_cursor": None,
        "total": 2,
    }


###############################################################################
def test_catalog_inventory_does_not_apply_execution_operation_or_point_scope() -> None:
    registry = _CapabilityRegistry()
    handler = CatalogToolHandler(
        capability_registry=registry,  # type: ignore[arg-type]
        runtime_registry=_RuntimeRegistry(),  # type: ignore[arg-type]
    )
    state = AgentRunState(
        request_id="request-inventory",
        conversation_id="conversation-inventory",
        phase=AgentPhase.BUILD_TOOL_CONTEXT,
        user_message="What map data can you show for Florence, Italy?",
        route=CapabilityRoute(
            primary_domain=CapabilityDomain.PROVIDER_DISCOVERY,
            secondary_domains=[
                CapabilityDomain.PLACE_SEARCH,
                CapabilityDomain.MAP_RENDERING,
            ],
            task_mode="execute",
            presentation="text",
            requires_location=True,
            capability_queries=[],
            operation="discover_available_map_data",
            target_refs=["Florence, Italy"],
            spatial_scope={"kind": "point", "target_refs": ["Florence, Italy"]},
        ),
    )

    result = asyncio.run(
        handler.discover(
            CapabilityDiscoveryInput(query="map data capabilities", limit=12),
            state,
        )
    )

    assert result.status == "success"
    assert registry.last_shortlist_kwargs["queries"] == []
    assert registry.last_shortlist_kwargs["operation"] is None
    assert registry.last_shortlist_kwargs["scope_kind"] is None
    assert registry.last_shortlist_kwargs["domains"] == {CapabilityDomain.MIXED}


###############################################################################
def test_catalog_inventory_page_matches_model_observation_limit() -> None:
    registry = _CapabilityRegistry()
    registry.items = [
        {"id": f"capability-{index}", "name": f"Capability {index}", "provider": "test"}
        for index in range(15)
    ]
    handler = CatalogToolHandler(
        capability_registry=registry,  # type: ignore[arg-type]
        runtime_registry=_RuntimeRegistry(),  # type: ignore[arg-type]
    )
    state = AgentRunState(
        request_id="request-paged-inventory",
        conversation_id="conversation-paged-inventory",
        phase=AgentPhase.BUILD_TOOL_CONTEXT,
        user_message="List the available map data capabilities.",
        route=CapabilityRoute(
            primary_domain=CapabilityDomain.PROVIDER_DISCOVERY,
            task_mode="execute",
            presentation="text",
            requires_location=False,
            operation="discover_available_map_data",
        ),
    )

    result = asyncio.run(
        handler.discover(CapabilityDiscoveryInput(limit=50), state)
    )

    assert result.status == "success"
    assert len(result.data["capabilities"]) == 12  # type: ignore[index]
    assert result.data["next_cursor"] == "12"  # type: ignore[index]
    assert result.data["total"] == 15  # type: ignore[index]
