from __future__ import annotations

from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response

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
from server.services.search.errors import (
    MapSearchExecutionError,
    MapSearchJobInitializationError,
    MapSearchJobNotFoundError,
    MapSearchTileProxyError,
)
from server.services.search.execution import MapSearchExecutionService
from server.common.constants import (
    MAPS_CATALOG_ROUTE,
    MAPS_JOB_ROUTE,
    MAPS_JOBS_ROUTE,
    MAPS_OSM_BASEMAP_TILE_ROUTE,
    MAPS_ROUTER_PREFIX,
    MAPS_SEARCH_ROUTE,
)

router = APIRouter(prefix=MAPS_ROUTER_PREFIX, tags=["search"])


def raise_map_search_http_error(error: MapSearchExecutionError) -> NoReturn:
    if isinstance(error, MapSearchJobNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
    if isinstance(error, MapSearchJobInitializationError):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(error),
        ) from error
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=str(error),
    ) from error


def get_search_execution(request: Request) -> MapSearchExecutionService:
    return request.app.state.search_runtime.search_execution


@router.get(
    MAPS_CATALOG_ROUTE,
    response_model=GeospatialCatalogResponse,
    status_code=status.HTTP_200_OK,
)
async def get_catalog(
    search_execution: MapSearchExecutionService = Depends(get_search_execution),
) -> GeospatialCatalogResponse:
    return GeospatialCatalogResponse.model_validate(
        await search_execution.get_catalog()
    )


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


@router.post(
    MAPS_JOBS_ROUTE,
    response_model=JobStartResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_search_job(
    payload: LocationSearchRequest,
    search_execution: MapSearchExecutionService = Depends(get_search_execution),
) -> JobStartResponse:
    try:
        return await search_execution.start_search_job(payload)
    except MapSearchExecutionError as error:
        raise_map_search_http_error(error)


@router.get(
    MAPS_JOB_ROUTE, response_model=JobStatusResponse, status_code=status.HTTP_200_OK
)
async def get_search_job_status(
    job_id: str,
    search_execution: MapSearchExecutionService = Depends(get_search_execution),
) -> JobStatusResponse:
    try:
        return await search_execution.get_search_job_status(job_id)
    except MapSearchExecutionError as error:
        raise_map_search_http_error(error)


@router.delete(
    MAPS_JOB_ROUTE, response_model=JobCancelResponse, status_code=status.HTTP_200_OK
)
async def cancel_search_job(
    job_id: str,
    search_execution: MapSearchExecutionService = Depends(get_search_execution),
) -> JobCancelResponse:
    try:
        return await search_execution.cancel_search_job(job_id)
    except MapSearchExecutionError as error:
        raise_map_search_http_error(error)
