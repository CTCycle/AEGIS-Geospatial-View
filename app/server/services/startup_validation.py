from __future__ import annotations

from server.common.typing import is_json_object
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

    missing_execution_contracts: list[str] = []
    for collection_name in (
        "basemaps",
        "overlays",
        "cameras",
        "transit",
        "tools",
    ):
        for item in getattr(catalog_snapshot, collection_name):
            capability_id = str(item.get("id") or "").strip()
            if (
                capability_id
                and runtime_registry.is_enabled(capability_id)
                and not is_json_object(item.get("executionContract"))
            ):
                missing_execution_contracts.append(capability_id)
    if missing_execution_contracts:
        raise RuntimeError(
            "Enabled executable capabilities missing execution contracts: "
            + ", ".join(sorted(missing_execution_contracts))
        )

    tool_registry = ToolRegistry(runtime_registry=runtime_registry)
    bindings = tool_registry.load_tool_bindings()
    tool_ids = {item["id"] for item in capability_registry.list_tools()}
    missing_bindings = [tool_id for tool_id in tool_ids if tool_id not in bindings]
    if missing_bindings:
        raise RuntimeError(
            "Missing tool bindings for: " + ", ".join(sorted(missing_bindings))
        )
