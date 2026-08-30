from __future__ import annotations

from server.services.geospatial.capability_registry import CapabilityRegistry
from server.services.geospatial.manifest_loader import GeospatialManifestLoader
from server.services.geospatial.runtime_registry import RuntimeRegistry


###############################################################################
class _NoCredentials:
    # -------------------------------------------------------------------------
    def get_active(self, *, provider: str, label: str):  # noqa: ANN201
        return None


###############################################################################
def test_tool_runtime_profiles_complete() -> None:
    capabilities = CapabilityRegistry()
    runtime = RuntimeRegistry(
        manifest_loader=GeospatialManifestLoader(),
        credentials_repo=_NoCredentials(),  # type: ignore[arg-type]
    )
    tools = capabilities.load_capabilities().tools
    profiles = runtime.build_snapshot().profiles
    for tool in tools:
        assert tool["id"] in profiles
