from __future__ import annotations

from server.services.agent.tool_registry import ToolRegistry
from server.domain.geospatial.registry import GeospatialManifestSnapshot
from server.services.geospatial.capability_registry import CapabilityRegistry
from server.services.geospatial.manifest_loader import GeospatialManifestLoader
from server.services.geospatial.runtime_registry import RuntimeRegistry
from server.repositories.credentials import CredentialRepository


###############################################################################
def run_startup_validations(credentials_repo: CredentialRepository) -> None:
    loader = GeospatialManifestLoader()
    catalog_snapshot = GeospatialManifestSnapshot.from_payload(loader.load_all())

    capability_registry = CapabilityRegistry.from_catalog_snapshot(catalog_snapshot)

    runtime_registry = RuntimeRegistry(
        catalog_snapshot=catalog_snapshot,
        credentials_repo=credentials_repo,
    )

    tool_registry = ToolRegistry(runtime_registry=runtime_registry)
    bindings = tool_registry.load_tool_bindings()
    tool_ids = {item["id"] for item in capability_registry.list_tools()}
    missing_bindings = [tool_id for tool_id in tool_ids if tool_id not in bindings]
    if missing_bindings:
        raise RuntimeError(
            "Missing tool bindings for: " + ", ".join(sorted(missing_bindings))
        )
