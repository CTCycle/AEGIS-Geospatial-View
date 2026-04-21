from __future__ import annotations

from dataclasses import dataclass

from AEGIS.server.services.geospatial.capability_registry import CapabilityRegistry
from AEGIS.server.services.geospatial.catalog import GeospatialCatalogService
from AEGIS.server.services.geospatial.runtime_registry import RuntimeRegistry
from AEGIS.server.services.geospatial.osm_tiles import OsmTileProxyService
from AEGIS.server.services.jobs import JobManager
from AEGIS.server.services.search.execution import MapSearchExecutionService
from AEGIS.server.services.search.orchestrator import LocationSearchOrchestrator


@dataclass(frozen=True)
class SearchRuntime:
    search_execution: MapSearchExecutionService
    search_orchestrator: LocationSearchOrchestrator
    job_manager: JobManager
    osm_tile_proxy_service: OsmTileProxyService


def build_search_runtime(job_manager: JobManager | None = None) -> SearchRuntime:
    capability_registry = CapabilityRegistry()
    runtime_registry = RuntimeRegistry()
    catalog_service = GeospatialCatalogService(
        capability_registry=capability_registry,
        runtime_registry=runtime_registry,
    )
    orchestrator = LocationSearchOrchestrator(capability_registry=capability_registry)
    resolved_job_manager = job_manager or JobManager()
    search_execution = MapSearchExecutionService(
        orchestrator=orchestrator,
        catalog_service=catalog_service,
        job_manager=resolved_job_manager,
    )
    return SearchRuntime(
        search_execution=search_execution,
        search_orchestrator=orchestrator,
        job_manager=resolved_job_manager,
        osm_tile_proxy_service=OsmTileProxyService(),
    )
