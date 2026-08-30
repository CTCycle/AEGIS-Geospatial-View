from __future__ import annotations

from dataclasses import dataclass

from server.services.geospatial.capability_registry import CapabilityRegistry
from server.services.geospatial.credential_resolver import GeospatialCredentialResolver
from server.services.geospatial.provider_registry import ProviderRegistry
from server.services.geospatial.render_descriptors import RenderDescriptorService
from server.services.search.orchestrator import LocationSearchOrchestrator


###############################################################################
@dataclass(frozen=True)
class SearchRuntime:
    search_orchestrator: LocationSearchOrchestrator
    capability_registry: CapabilityRegistry
    provider_registry: ProviderRegistry


###############################################################################
def build_search_runtime(
    capability_registry: CapabilityRegistry | None = None,
    provider_registry: ProviderRegistry | None = None,
    credential_resolver: GeospatialCredentialResolver | None = None,
) -> SearchRuntime:
    resolved_capability_registry = capability_registry or CapabilityRegistry()
    resolved_provider_registry = provider_registry or ProviderRegistry(
        credential_resolver=credential_resolver,
    )
    render_descriptor_service = RenderDescriptorService(
        capability_registry=resolved_capability_registry,
        provider_registry=resolved_provider_registry,
        credential_resolver=credential_resolver,
    )
    orchestrator = LocationSearchOrchestrator(
        capability_registry=resolved_capability_registry,
        render_descriptor_service=render_descriptor_service,
    )
    return SearchRuntime(
        search_orchestrator=orchestrator,
        capability_registry=resolved_capability_registry,
        provider_registry=resolved_provider_registry,
    )
