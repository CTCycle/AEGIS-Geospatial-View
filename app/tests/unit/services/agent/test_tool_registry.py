from __future__ import annotations

import asyncio

from server.domain.agent.decision import ExecutionPlan, ResolvedLocation
from server.services.agent.tool_registry import ToolRegistry
from server.services.geospatial.capability_registry import CapabilityRegistry
from server.services.geospatial.manifest_loader import GeospatialManifestLoader
from server.services.geospatial.runtime_registry import RuntimeRegistry

###############################################################################
class _Credentials:

    # -------------------------------------------------------------------------
    def get_active(self, *, provider: str, label: str):  # noqa: ANN001
        _ = provider, label
        return None

###############################################################################
def _registry() -> ToolRegistry:
    return ToolRegistry(
        runtime_registry=RuntimeRegistry(
            manifest_loader=GeospatialManifestLoader(),
            credentials_repo=_Credentials(),  # type: ignore[arg-type]
        )
    )

###############################################################################
def test_tool_registry_executes_coordinates() -> None:
    registry = _registry()
    plan = ExecutionPlan(state="direct_tool", mode="direct_text", action_id="location_lookup", tool_id="location_to_coordinates")
    location = ResolvedLocation(label="Rome", latitude=41.9, longitude=12.5)

    async def _run() -> None:
        payload = await registry.execute("location_to_coordinates", plan, location)
        assert payload["tool_id"] == "location_to_coordinates"

    asyncio.run(_run())

###############################################################################
def test_tool_registry_has_binding_for_all_direct_tool_capabilities() -> None:
    registry = _registry()
    bindings = registry.load_tool_bindings()
    tools = CapabilityRegistry().load_capabilities().tools
    tool_ids = {str(item.get("id")) for item in tools}
    assert tool_ids.issubset(set(bindings.keys()))
