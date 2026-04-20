from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import Response

from AEGIS.server.domain.geographics import (
    GeospatialCatalogResponse,
    LocationSearchRequest,
    SearchByLocationResponse,
)
from AEGIS.server.domain.jobs import (
    JobCancelResponse,
    JobStartResponse,
    JobStatusResponse,
)
from AEGIS.server.services.search.execution import MapSearchExecutionService
from AEGIS.server.common.constants import (
    MAPS_CATALOG_ROUTE,
    MAPS_JOB_ROUTE,
    MAPS_JOBS_ROUTE,
    MAPS_OSM_BASEMAP_TILE_ROUTE,
    MAPS_ROUTER_PREFIX,
    MAPS_SEARCH_ROUTE,
)

router = APIRouter(prefix=MAPS_ROUTER_PREFIX, tags=["search"])


def get_search_execution(request: Request) -> MapSearchExecutionService:
    return request.app.state.search_runtime.search_execution


@router.get(MAPS_CATALOG_ROUTE, response_model=GeospatialCatalogResponse, status_code=status.HTTP_200_OK)
async def get_catalog(
    search_execution: MapSearchExecutionService = Depends(get_search_execution),
) -> GeospatialCatalogResponse:
    return await search_execution.get_catalog()


@router.get(MAPS_OSM_BASEMAP_TILE_ROUTE, include_in_schema=False)
def proxy_osm_basemap_tile(request: Request, z: int, x: int, y: int) -> Response:
    if z < 0 or x < 0 or y < 0:
        return Response(status_code=status.HTTP_400_BAD_REQUEST)
    try:
        tile, media_type, cache_control = (
            request.app.state.search_runtime.osm_tile_proxy_service.fetch_tile(z, x, y)
        )
        return Response(
            content=tile,
            media_type=media_type,
            headers={"Cache-Control": cache_control},
        )
    except Exception as exc:
        return Response(
            content=str(exc) or "OSM basemap tile provider is unavailable.",
            status_code=status.HTTP_502_BAD_GATEWAY,
            media_type="text/plain",
        )


@router.post(MAPS_SEARCH_ROUTE, response_model=SearchByLocationResponse, status_code=status.HTTP_200_OK)
async def search_by_location(
    payload: LocationSearchRequest,
    search_execution: MapSearchExecutionService = Depends(get_search_execution),
) -> SearchByLocationResponse:
    return await search_execution.search_by_location(payload)


@router.post(MAPS_JOBS_ROUTE, response_model=JobStartResponse, status_code=status.HTTP_202_ACCEPTED)
async def start_search_job(
    payload: LocationSearchRequest,
    search_execution: MapSearchExecutionService = Depends(get_search_execution),
) -> JobStartResponse:
    return await search_execution.start_search_job(payload)


@router.get(MAPS_JOB_ROUTE, response_model=JobStatusResponse, status_code=status.HTTP_200_OK)
async def get_search_job_status(
    job_id: str,
    search_execution: MapSearchExecutionService = Depends(get_search_execution),
) -> JobStatusResponse:
    return await search_execution.get_search_job_status(job_id)


@router.delete(MAPS_JOB_ROUTE, response_model=JobCancelResponse, status_code=status.HTTP_200_OK)
async def cancel_search_job(
    job_id: str,
    search_execution: MapSearchExecutionService = Depends(get_search_execution),
) -> JobCancelResponse:
    return await search_execution.cancel_search_job(job_id)
