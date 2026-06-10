from __future__ import annotations

from dataclasses import dataclass

from server.services.geospatial.capability_registry import CapabilityRegistry
from server.services.geospatial.catalog import GeospatialCatalogService
from server.services.geospatial.osm_tiles import OsmTileProxyService
from server.services.geospatial.runtime_registry import RuntimeRegistry
from server.services.search.execution import MapSearchExecutionService
from server.services.search.orchestrator import LocationSearchOrchestrator


###############################################################################
@dataclass(frozen=True)
class SearchRuntime:
    search_execution: MapSearchExecutionService
    search_orchestrator: LocationSearchOrchestrator
    osm_tile_proxy_service: OsmTileProxyService


###############################################################################
def build_search_runtime() -> SearchRuntime:
    capability_registry = CapabilityRegistry()
    runtime_registry = RuntimeRegistry()
    catalog_service = GeospatialCatalogService(
        capability_registry=capability_registry,
        runtime_registry=runtime_registry,
    )
    orchestrator = LocationSearchOrchestrator(capability_registry=capability_registry)
    osm_tile_proxy_service = OsmTileProxyService()
    search_execution = MapSearchExecutionService(
        orchestrator=orchestrator,
        catalog_service=catalog_service,
        osm_tile_proxy_service=osm_tile_proxy_service,
    )
    return SearchRuntime(
        search_execution=search_execution,
        search_orchestrator=orchestrator,
        osm_tile_proxy_service=osm_tile_proxy_service,
    )
