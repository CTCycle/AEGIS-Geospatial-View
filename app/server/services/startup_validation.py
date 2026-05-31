from __future__ import annotations

from server.configurations import ServerSettings, get_server_settings
from server.services.agent.tool_registry import ToolRegistry
from server.services.geospatial.capability_registry import CapabilityRegistry
from server.services.geospatial.manifest_loader import GeospatialManifestLoader
from server.services.geospatial.runtime_registry import RuntimeRegistry


def run_startup_validations(settings: ServerSettings | None = None) -> None:
    resolved_settings = settings or get_server_settings()
    if not resolved_settings.credential_master_key:
        raise RuntimeError("Credential master key must be configured.")
    if not resolved_settings.credential_key_version:
        raise RuntimeError("Credential key version must be configured.")

    loader = GeospatialManifestLoader()
    loader.load_all()

    capability_registry = CapabilityRegistry(manifest_loader=loader)
    capability_registry.load_capabilities()

    runtime_registry = RuntimeRegistry(manifest_loader=loader)
    runtime_registry.build_snapshot()

    tool_registry = ToolRegistry(runtime_registry=runtime_registry)
    bindings = tool_registry.load_tool_bindings()
    tool_ids = {item["id"] for item in capability_registry.list_tools()}
    missing_bindings = [tool_id for tool_id in tool_ids if tool_id not in bindings]
    if missing_bindings:
        raise RuntimeError(
            "Missing tool bindings for: " + ", ".join(sorted(missing_bindings))
        )
