"""Native-v2 capability discovery handler."""

from __future__ import annotations

import time
from typing import Any

from server.domain.agent.capability_domains import CapabilityDomain
from server.domain.agent.capability_route import AgentState
from server.domain.agent.tool_result import ToolExecutionMetadata, ToolResult
from server.services.agent.tool_definitions import CapabilityDiscoveryInput
from server.services.geospatial.capability_registry import CapabilityRegistry
from server.services.geospatial.runtime_registry import RuntimeRegistry


###############################################################################
class CatalogToolHandler:

    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        capability_registry: CapabilityRegistry,
        runtime_registry: RuntimeRegistry,
    ) -> None:
        self.capability_registry = capability_registry
        self.runtime_registry = runtime_registry

    # -------------------------------------------------------------------------
    async def discover(
        self,
        request: CapabilityDiscoveryInput,
        state: AgentState,
    ) -> ToolResult:
        started = time.perf_counter()
        route_domains = {CapabilityDomain.MIXED}
        if state.route is not None:
            route_domains = {state.route.primary_domain, *state.route.secondary_domains}
        candidates = self.capability_registry.shortlist(
            domains=route_domains,
            queries=[request.query] if request.query else [],
            explicit_ids=request.capability_ids,
            runtime_registry=self.runtime_registry,
            limit=request.limit,
        )
        if request.provider_id:
            provider_id = request.provider_id.casefold()
            candidates = [
                item
                for item in candidates
                if str(item.get("provider") or "").casefold() == provider_id
            ]
        descriptors = [_descriptor(self.capability_registry, item) for item in candidates]
        discovered_ids = [str(item["id"]) for item in descriptors if item.get("id")]
        state.capability_ids = list(
            dict.fromkeys([*state.capability_ids, *discovered_ids])
        )[:12]
        status = "success" if descriptors else "valid_empty"
        return ToolResult(
            call_id="handler-call",
            tool_name="discover_geospatial_capabilities",
            status=status,
            summary=(
                f"Found {len(descriptors)} eligible capabilities."
                if descriptors
                else "No eligible capabilities matched the request."
            ),
            data={
                "capabilities": descriptors,
                "provider_id": request.provider_id,
                "include_provider_layers": request.include_provider_layers,
                "next_cursor": None,
            },
            metadata=ToolExecutionMetadata(
                duration_ms=max(0, int((time.perf_counter() - started) * 1000))
            ),
        )


###############################################################################
def _descriptor(
    registry: CapabilityRegistry, capability: dict[str, Any]
) -> dict[str, Any]:
    capability_id = str(capability.get("id") or "").strip()
    return {
        "id": capability_id,
        "name": str(capability.get("name") or capability_id),
        "description": str(capability.get("description") or "")[:500],
        "provider": str(capability.get("provider") or ""),
        "kind": str(
            capability.get("capabilityKind")
            or capability.get("capability_kind")
            or capability.get("type")
            or "unknown"
        ),
        "supports_map": bool(
            capability.get("supports_map", True)
        ),
        "execution_contract": registry.execution_contract(capability_id),
    }


__all__ = ["CatalogToolHandler"]
