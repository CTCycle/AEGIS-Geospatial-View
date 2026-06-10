from __future__ import annotations

from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response

from server.common.paths import (
    MAPS_CATALOG_ROUTE,
    MAPS_JOB_ROUTE,
    MAPS_JOBS_ROUTE,
    MAPS_OSM_BASEMAP_TILE_ROUTE,
    MAPS_ROUTER_PREFIX,
    MAPS_SEARCH_ROUTE,
)
from server.domain.geographics import (
    GeospatialCatalogResponse,
    LocationSearchRequest,
    SearchByLocationResponse,
)
from server.domain.jobs import (
    JobCancelResponse,
    JobStartResponse,
    JobStatusResponse,
)
from server.services.jobs import BackgroundJobService
from server.services.search.errors import (
    MapSearchExecutionError,
    MapSearchJobInitializationError,
    MapSearchJobNotFoundError,
    MapSearchTileProxyError,
)
from server.services.search.execution import MapSearchExecutionService

router = APIRouter(prefix=MAPS_ROUTER_PREFIX, tags=["search"])

MAP_SEARCH_ERROR_STATUS = {
    MapSearchJobNotFoundError: status.HTTP_404_NOT_FOUND,
    MapSearchJobInitializationError: status.HTTP_500_INTERNAL_SERVER_ERROR,
}


###############################################################################
def raise_map_search_http_error(error: MapSearchExecutionError) -> NoReturn:
    status_code = next(
        (
            mapped_status
            for error_type, mapped_status in MAP_SEARCH_ERROR_STATUS.items()
            if isinstance(error, error_type)
        ),
        status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
    raise HTTPException(
        status_code=status_code,
        detail=str(error),
    ) from error


###############################################################################
def get_search_execution(request: Request) -> MapSearchExecutionService:
    return request.app.state.search_runtime.search_execution


###############################################################################
def get_job_service(request: Request) -> BackgroundJobService:
    return request.app.state.job_service


###############################################################################
@router.get(
    MAPS_CATALOG_ROUTE,
    response_model=GeospatialCatalogResponse,
    status_code=status.HTTP_200_OK,
)
async def get_catalog(
    search_execution: MapSearchExecutionService = Depends(get_search_execution),
) -> GeospatialCatalogResponse:
    return await search_execution.get_catalog()


###############################################################################
@router.get(MAPS_OSM_BASEMAP_TILE_ROUTE, include_in_schema=False)
def proxy_osm_basemap_tile(
    z: int,
    x: int,
    y: int,
    search_execution: MapSearchExecutionService = Depends(get_search_execution),
) -> Response:
    if z < 0 or x < 0 or y < 0:
        return Response(status_code=status.HTTP_400_BAD_REQUEST)
    try:
        tile, media_type, cache_control = search_execution.fetch_osm_basemap_tile(
            z, x, y
        )
        return Response(
            content=tile,
            media_type=media_type,
            headers={"Cache-Control": cache_control},
        )
    except MapSearchTileProxyError as exc:
        return Response(
            content=str(exc) or "OSM basemap tile provider is unavailable.",
            status_code=status.HTTP_502_BAD_GATEWAY,
            media_type="text/plain",
        )


###############################################################################
@router.post(
    MAPS_SEARCH_ROUTE,
    response_model=SearchByLocationResponse,
    status_code=status.HTTP_200_OK,
)
async def search_by_location(
    payload: LocationSearchRequest,
    search_execution: MapSearchExecutionService = Depends(get_search_execution),
) -> SearchByLocationResponse:
    return await search_execution.search_by_location(payload)


###############################################################################
@router.post(
    MAPS_JOBS_ROUTE,
    response_model=JobStartResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_search_job(
    payload: LocationSearchRequest,
    job_service: BackgroundJobService = Depends(get_job_service),
) -> JobStartResponse:
    return job_service.create_map_job(payload)


###############################################################################
@router.get(
    MAPS_JOB_ROUTE, response_model=JobStatusResponse, status_code=status.HTTP_200_OK
)
async def get_search_job_status(
    job_id: str,
    job_service: BackgroundJobService = Depends(get_job_service),
) -> JobStatusResponse:
    response = job_service.get_job(job_id)
    if response is None:
        raise_map_search_http_error(MapSearchJobNotFoundError(f"Job not found: {job_id}"))
    return response


###############################################################################
@router.delete(
    MAPS_JOB_ROUTE, response_model=JobCancelResponse, status_code=status.HTTP_200_OK
)
async def cancel_search_job(
    job_id: str,
    job_service: BackgroundJobService = Depends(get_job_service),
) -> JobCancelResponse:
    response = job_service.cancel_job(job_id)
    if response is None:
        raise_map_search_http_error(MapSearchJobNotFoundError(f"Job not found: {job_id}"))
    return response
