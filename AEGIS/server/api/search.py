from __future__ import annotations

from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import APIRouter, status
from fastapi.responses import Response

from AEGIS.server.configurations import get_server_settings
from AEGIS.server.domain.geographics import (
    GeospatialCatalogResponse,
    SearchByLocationResponse,
)
from AEGIS.server.domain.jobs import (
    JobCancelResponse,
    JobStartResponse,
    JobStatusResponse,
)
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
from AEGIS.server.services.jobs import job_manager
from AEGIS.server.services.sanitization import LocationSanitizationService
from AEGIS.server.services.search.execution import MapSearchExecutionService
from AEGIS.server.utils.constants import (
    MAPS_CATALOG_ROUTE,
    MAPS_JOB_ROUTE,
    MAPS_JOBS_ROUTE,
    MAPS_OSM_BASEMAP_TILE_ROUTE,
    MAPS_ROUTER_PREFIX,
    MAPS_SEARCH_ROUTE,
)

router = APIRouter(prefix=MAPS_ROUTER_PREFIX, tags=["search"])

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
search_execution = MapSearchExecutionService(
    router=router,
    sanitization_service=sanitization_service,
    nominatim_service=nominatim_service,
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


###############################################################################
@router.get(MAPS_OSM_BASEMAP_TILE_ROUTE, include_in_schema=False)
def proxy_osm_basemap_tile(z: int, x: int, y: int) -> Response:
    if z < 0 or x < 0 or y < 0:
        return Response(status_code=status.HTTP_400_BAD_REQUEST)

    tile_url = f"https://tile.openstreetmap.org/{z}/{x}/{y}.png"
    request = Request(
        tile_url,
        headers={
            "User-Agent": "AEGIS Geospatial View/2.0 (+https://github.com/CTCycle/AEGIS-geographics)",
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        },
    )
    try:
        with urlopen(request, timeout=10) as upstream:
            media_type = upstream.headers.get_content_type() or "image/png"
            cache_control = upstream.headers.get(
                "Cache-Control", "public, max-age=3600"
            )
            return Response(
                content=upstream.read(),
                media_type=media_type,
                headers={"Cache-Control": cache_control},
            )
    except HTTPError as exc:
        detail = f"OSM basemap tile request failed with status {exc.code}."
        return Response(
            content=detail,
            status_code=status.HTTP_502_BAD_GATEWAY,
            media_type="text/plain",
        )
    except URLError:
        return Response(
            content="OSM basemap tile provider is unavailable.",
            status_code=status.HTTP_502_BAD_GATEWAY,
            media_type="text/plain",
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
