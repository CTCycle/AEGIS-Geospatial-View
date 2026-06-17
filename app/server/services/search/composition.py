from __future__ import annotations

from dataclasses import dataclass

from server.services.geospatial.capability_registry import CapabilityRegistry
from server.services.search.orchestrator import LocationSearchOrchestrator


###############################################################################
@dataclass(frozen=True)
class SearchRuntime:
    search_orchestrator: LocationSearchOrchestrator


###############################################################################
def build_search_runtime() -> SearchRuntime:
    capability_registry = CapabilityRegistry()
    orchestrator = LocationSearchOrchestrator(capability_registry=capability_registry)
    return SearchRuntime(
        search_orchestrator=orchestrator,
    )
