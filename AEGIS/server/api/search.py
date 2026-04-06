from __future__ import annotations

from fastapi import APIRouter, status

from AEGIS.server.configurations import server_settings
from AEGIS.server.domain.geographics import GeospatialCatalogResponse, SearchByLocationResponse
from AEGIS.server.domain.jobs import JobCancelResponse, JobStartResponse, JobStatusResponse
from AEGIS.server.services.geospatial.catalog import GeospatialCatalogService
from AEGIS.server.services.geospatial.elevation import OpenElevationService
from AEGIS.server.services.geospatial.gibs import GIBSService
from AEGIS.server.services.geospatial.layers import LayerProviderService
from AEGIS.server.services.geospatial.maps import MapService
from AEGIS.server.services.geospatial.normatim import NormatimService
from AEGIS.server.services.geospatial.openaq import OpenAQService
from AEGIS.server.services.geospatial.pvgis import PVGISService
from AEGIS.server.services.geospatial.rendering import MapRenderingService, MapSearchToolkit
from AEGIS.server.services.jobs import job_manager
from AEGIS.server.services.sanitization import LocationSanitizationService
from AEGIS.server.services.search.execution import MapSearchExecutionService
from AEGIS.server.utils.constants import (
    MAPS_CATALOG_ROUTE,
    MAPS_JOB_ROUTE,
    MAPS_JOBS_ROUTE,
    MAPS_ROUTER_PREFIX,
    MAPS_SEARCH_ROUTE,
)

router = APIRouter(prefix=MAPS_ROUTER_PREFIX, tags=["search"])

sanitization_service = LocationSanitizationService()
normatim_service = NormatimService()
gibs_service = GIBSService()
map_service = MapService()
layer_service = LayerProviderService(
    metadata_provider=gibs_service.resolve_layer_meters_per_pixel
)
elevation_service = OpenElevationService()
openaq_service = OpenAQService()
pvgis_service = PVGISService()
catalog_service = GeospatialCatalogService(
    openaq_service=openaq_service,
    pvgis_service=pvgis_service,
)

toolkit = MapSearchToolkit(
    gibs_service=gibs_service,
    default_layer=server_settings.gibs.default_layer,
)
rendering_service = MapRenderingService(
    toolkit=toolkit,
    map_service=map_service,
    gibs_service=gibs_service,
    layer_service=layer_service,
)
search_execution = MapSearchExecutionService(
    router=router,
    sanitization_service=sanitization_service,
    normatim_service=normatim_service,
    toolkit=toolkit,
    rendering_service=rendering_service,
    job_manager=job_manager,
    catalog_service=catalog_service,
    elevation_service=elevation_service,
)
search_endpoint = search_execution

router.add_api_route(
    MAPS_CATALOG_ROUTE,
    search_execution.get_catalog,
    methods=["GET"],
    response_model=GeospatialCatalogResponse,
    status_code=status.HTTP_200_OK,
)
router.add_api_route(
    MAPS_SEARCH_ROUTE,
    search_execution.search_by_location,
    methods=["POST"],
    response_model=SearchByLocationResponse,
    status_code=status.HTTP_200_OK,
)
router.add_api_route(
    MAPS_JOBS_ROUTE,
    search_execution.start_search_job,
    methods=["POST"],
    response_model=JobStartResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
router.add_api_route(
    MAPS_JOB_ROUTE,
    search_execution.get_search_job_status,
    methods=["GET"],
    response_model=JobStatusResponse,
    status_code=status.HTTP_200_OK,
)
router.add_api_route(
    MAPS_JOB_ROUTE,
    search_execution.cancel_search_job,
    methods=["DELETE"],
    response_model=JobCancelResponse,
    status_code=status.HTTP_200_OK,
)
