from __future__ import annotations

import asyncio

from server.domain.agent.decision import ExecutionPlan, ResolvedLocation
from server.services.agent.tool_registry import ToolRegistry
from server.services.geospatial.capability_registry import CapabilityRegistry


def test_tool_registry_executes_coordinates() -> None:
    registry = ToolRegistry()
    plan = ExecutionPlan(state="direct_tool", mode="direct_text", action_id="location_lookup", tool_id="location_to_coordinates")
    location = ResolvedLocation(label="Rome", latitude=41.9, longitude=12.5)

    async def _run() -> None:
        payload = await registry.execute("location_to_coordinates", plan, location)
        assert payload["tool_id"] == "location_to_coordinates"

    asyncio.run(_run())


def test_tool_registry_has_binding_for_all_direct_tool_capabilities() -> None:
    registry = ToolRegistry()
    bindings = registry.load_tool_bindings()
    tools = CapabilityRegistry().load_capabilities().tools
    tool_ids = {str(item.get("id")) for item in tools}
    assert tool_ids.issubset(set(bindings.keys()))
