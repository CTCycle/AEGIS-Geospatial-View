from __future__ import annotations

from datetime import datetime, time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest, urlopen

from fastapi import APIRouter, Body, Depends, Request, status
from fastapi.responses import Response

from AEGIS.server.domain.geographics import (
    GeospatialCatalogResponse,
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
def proxy_osm_basemap_tile(z: int, x: int, y: int) -> Response:
    if z < 0 or x < 0 or y < 0:
        return Response(status_code=status.HTTP_400_BAD_REQUEST)

    tile_url = f"https://tile.openstreetmap.org/{z}/{x}/{y}.png"
    request = UrlRequest(
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


@router.post(MAPS_SEARCH_ROUTE, response_model=SearchByLocationResponse, status_code=status.HTTP_200_OK)
async def search_by_location(
    datetime_value: datetime | str | None = Body(default=None, alias="datetime"),
    time_of_day: time | str | None = Body(default=None),
    timeline_year: int | None = Body(default=None),
    country: str | None = Body(default=None),
    city: str | None = Body(default=None),
    address: str | None = Body(default=None),
    use_coordinates: bool = Body(default=False),
    latitude: float | None = Body(default=None),
    longitude: float | None = Body(default=None),
    geospatial_layers: list[str] = Body(default_factory=list),
    basemap_id: str | None = Body(default=None),
    overlay_ids: list[str] = Body(default_factory=list),
    aoi: dict[str, Any] | None = Body(default=None),
    commute: dict[str, Any] | None = Body(default=None),
    bbox: list[float] | None = Body(default=None),
    radius_m: float | None = Body(default=None),
    map_size_m: float | None = Body(default=None),
    map_tiles: str | None = Body(default=None),
    image_width: int | None = Body(default=None),
    image_height: int | None = Body(default=None),
    image_crs: str | None = Body(default=None),
    image_format: str | None = Body(default=None),
    search_execution: MapSearchExecutionService = Depends(get_search_execution),
) -> SearchByLocationResponse:
    return await search_execution.search_by_location(
        datetime_value=datetime_value,
        time_of_day=time_of_day,
        timeline_year=timeline_year,
        country=country,
        city=city,
        address=address,
        use_coordinates=use_coordinates,
        latitude=latitude,
        longitude=longitude,
        geospatial_layers=geospatial_layers,
        basemap_id=basemap_id,
        overlay_ids=overlay_ids,
        aoi=aoi,
        commute=commute,
        bbox=bbox,
        radius_m=radius_m,
        map_size_m=map_size_m,
        map_tiles=map_tiles,
        image_width=image_width,
        image_height=image_height,
        image_crs=image_crs,
        image_format=image_format,
    )


@router.post(MAPS_JOBS_ROUTE, response_model=JobStartResponse, status_code=status.HTTP_202_ACCEPTED)
async def start_search_job(
    datetime_value: datetime | str | None = Body(default=None, alias="datetime"),
    time_of_day: time | str | None = Body(default=None),
    timeline_year: int | None = Body(default=None),
    country: str | None = Body(default=None),
    city: str | None = Body(default=None),
    address: str | None = Body(default=None),
    use_coordinates: bool = Body(default=False),
    latitude: float | None = Body(default=None),
    longitude: float | None = Body(default=None),
    geospatial_layers: list[str] = Body(default_factory=list),
    basemap_id: str | None = Body(default=None),
    overlay_ids: list[str] = Body(default_factory=list),
    aoi: dict[str, Any] | None = Body(default=None),
    commute: dict[str, Any] | None = Body(default=None),
    bbox: list[float] | None = Body(default=None),
    radius_m: float | None = Body(default=None),
    map_size_m: float | None = Body(default=None),
    map_tiles: str | None = Body(default=None),
    image_width: int | None = Body(default=None),
    image_height: int | None = Body(default=None),
    image_crs: str | None = Body(default=None),
    image_format: str | None = Body(default=None),
    search_execution: MapSearchExecutionService = Depends(get_search_execution),
) -> JobStartResponse:
    return await search_execution.start_search_job(
        datetime_value=datetime_value,
        time_of_day=time_of_day,
        timeline_year=timeline_year,
        country=country,
        city=city,
        address=address,
        use_coordinates=use_coordinates,
        latitude=latitude,
        longitude=longitude,
        geospatial_layers=geospatial_layers,
        basemap_id=basemap_id,
        overlay_ids=overlay_ids,
        aoi=aoi,
        commute=commute,
        bbox=bbox,
        radius_m=radius_m,
        map_size_m=map_size_m,
        map_tiles=map_tiles,
        image_width=image_width,
        image_height=image_height,
        image_crs=image_crs,
        image_format=image_format,
    )


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