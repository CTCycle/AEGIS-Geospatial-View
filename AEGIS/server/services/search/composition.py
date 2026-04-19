from __future__ import annotations

from dataclasses import dataclass

from AEGIS.server.configurations import get_server_settings
from AEGIS.server.services.geospatial.catalog import GeospatialCatalogService
from AEGIS.server.services.geospatial.elevation import OpenElevationService
from AEGIS.server.services.geospatial.gibs import GIBSService
from AEGIS.server.services.geospatial.layers import LayerProviderService
from AEGIS.server.services.geospatial.maps import MapService
from AEGIS.server.services.geospatial.nominatim import NominatimService
from AEGIS.server.services.geospatial.openaq import OpenAQService
from AEGIS.server.services.geospatial.openmeteo import OpenMeteoService
from AEGIS.server.services.geospatial.overpass import OverpassService
from AEGIS.server.services.geospatial.pvgis import PVGISService
from AEGIS.server.services.geospatial.rainviewer import RainViewerService
from AEGIS.server.services.geospatial.rendering import (
    MapRenderingService,
    MapSearchToolkit,
)
from AEGIS.server.services.jobs import JobManager
from AEGIS.server.services.sanitization import LocationSanitizationService
from AEGIS.server.services.search.execution import MapSearchExecutionService
from AEGIS.server.services.search.orchestrator import LocationSearchOrchestrator


@dataclass(frozen=True)
class SearchRuntime:
    search_execution: MapSearchExecutionService
    search_orchestrator: LocationSearchOrchestrator
    job_manager: JobManager


def build_search_runtime(job_manager: JobManager | None = None) -> SearchRuntime:
    sanitization_service = LocationSanitizationService()
    nominatim_service = NominatimService()
    gibs_service = GIBSService()
    map_service = MapService()
    layer_service = LayerProviderService(
        metadata_provider=gibs_service.resolve_layer_meters_per_pixel
    )
    elevation_service = OpenElevationService()
    openaq_service = OpenAQService()
    pvgis_service = PVGISService()
    openmeteo_service = OpenMeteoService()
    overpass_service = OverpassService()
    rainviewer_service = RainViewerService()
    catalog_service = GeospatialCatalogService(
        openaq_service=openaq_service,
        pvgis_service=pvgis_service,
        openmeteo_service=openmeteo_service,
        overpass_service=overpass_service,
        rainviewer_service=rainviewer_service,
    )

    toolkit = MapSearchToolkit(
        gibs_service=gibs_service,
        default_layer=get_server_settings().gibs.default_layer,
    )
    rendering_service = MapRenderingService(
        toolkit=toolkit,
        map_service=map_service,
        gibs_service=gibs_service,
        layer_service=layer_service,
    )

    resolved_job_manager = job_manager or JobManager()
    search_execution = MapSearchExecutionService(
        sanitization_service=sanitization_service,
        nominatim_service=nominatim_service,
        toolkit=toolkit,
        rendering_service=rendering_service,
        job_manager=resolved_job_manager,
        catalog_service=catalog_service,
        elevation_service=elevation_service,
    )
    return SearchRuntime(
        search_execution=search_execution,
        search_orchestrator=search_execution.orchestrator,
        job_manager=resolved_job_manager,
    )