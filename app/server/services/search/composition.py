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
    *,
    capability_registry: CapabilityRegistry,
    provider_registry: ProviderRegistry,
    credential_resolver: GeospatialCredentialResolver,
) -> SearchRuntime:
    render_descriptor_service = RenderDescriptorService(
        capability_registry=capability_registry,
        provider_registry=provider_registry,
        credential_resolver=credential_resolver,
    )
    orchestrator = LocationSearchOrchestrator(
        capability_registry=capability_registry,
        render_descriptor_service=render_descriptor_service,
    )
    return SearchRuntime(
        search_orchestrator=orchestrator,
        capability_registry=capability_registry,
        provider_registry=provider_registry,
    )
