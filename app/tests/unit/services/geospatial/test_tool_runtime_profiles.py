from __future__ import annotations

from server.services.geospatial.capability_registry import CapabilityRegistry
from server.services.geospatial.runtime_registry import RuntimeRegistry


###############################################################################
def test_tool_runtime_profiles_complete() -> None:
    capabilities = CapabilityRegistry()
    runtime = RuntimeRegistry()
    tools = capabilities.load_capabilities().tools
    profiles = runtime.build_snapshot().profiles
    for tool in tools:
        assert tool["id"] in profiles
