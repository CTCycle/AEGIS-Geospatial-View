from __future__ import annotations

import asyncio
import json
from datetime import datetime, time
from typing import Any, Mapping, Sequence

from fastapi import APIRouter, Body, HTTPException, status
from pydantic import ValidationError

from AEGIS.server.configurations import get_server_settings
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
from AEGIS.server.repositories.serialization import DataSerializer
from AEGIS.server.services.geospatial.catalog import GeospatialCatalogService
from AEGIS.server.services.geospatial.elevation import OpenElevationService
from AEGIS.server.services.geospatial.gibs import GIBSRequestError, GIBSValidationError
from AEGIS.server.services.geospatial.layers import LayerProviderError
from AEGIS.server.services.geospatial.maps import MapRequestError, MapValidationError
from AEGIS.server.services.geospatial.nominatim import NominatimService
from AEGIS.server.services.geospatial.rendering import (
    CoordinatePair,
    MapRenderingService,
    MapSearchToolkit,
)
from AEGIS.server.services.jobs import JobManager
from AEGIS.server.services.sanitization import LocationSanitizationService
from AEGIS.server.services.search.factory import (
    build_location_search_payload_data,
    build_request_context,
    build_search_response,
)
from AEGIS.server.services.search.orchestrator import LocationSearchOrchestrator
from AEGIS.server.utils.constants import (
    JOB_STATUS_CANCELLED,
    MAP_SEARCH_CANCELLATION_NOT_ALLOWED,
    MAP_SEARCH_CANCELLATION_REQUESTED,
    MAP_SEARCH_JOB_INIT_ERROR,
    MAP_SEARCH_JOB_PROGRESS_COORDINATES,
    MAP_SEARCH_JOB_PROGRESS_IMAGERY,
    MAP_SEARCH_JOB_PROGRESS_PERSISTED,
    MAP_SEARCH_JOB_PROGRESS_POSTPROCESS,
    MAP_SEARCH_JOB_START_MESSAGE,
)
from AEGIS.server.utils.logger import logger


def sanitize_validation_errors(
    errors: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    sanitized: list[dict[str, Any]] = []
    for error in errors:
        normalized = dict(error)
        context = normalized.get("ctx")
        if isinstance(context, dict):
            normalized["ctx"] = {key: str(value) for key, value in context.items()}
        sanitized.append(normalized)
    return sanitized


def run_map_search_job(
    service: "MapSearchExecutionService",
    payload: LocationSearchRequest,
    request_context: dict[str, Any],
    job_id: str,
) -> dict[str, Any]:
    return asyncio.run(
        service.process_location_search_job(
            payload=payload,
            request_context=request_context,
            job_id=job_id,
        )
    )


class MapSearchExecutionService:
    def __init__(
        self,
        router: APIRouter,
        sanitization_service: LocationSanitizationService,
        nominatim_service: NominatimService,
        toolkit: MapSearchToolkit,
        rendering_service: MapRenderingService,
        job_manager: JobManager,
        catalog_service: GeospatialCatalogService,
        elevation_service: OpenElevationService,
    ) -> None:
        self.router = router
        self.sanitization_service = sanitization_service
        self.nominatim_service = nominatim_service
        self.toolkit = toolkit
        self.renderer = rendering_service
        self.job_manager = job_manager
        self.catalog_service = catalog_service
        self.elevation_service = elevation_service
        self.serializer = DataSerializer()
        self.orchestrator = LocationSearchOrchestrator(
            sanitization_service=sanitization_service,
            nominatim_service=nominatim_service,
            catalog_service=catalog_service,
            elevation_service=elevation_service,
            renderer=rendering_service,
            toolkit=toolkit,
        )

    def resolve_coordinate_pair(
        self,
        payload: LocationSearchRequest | None,
        response_payload: dict[str, Any] | None,
        fallback: dict[str, Any],
    ) -> CoordinatePair | None:
        payload_snapshot = (
            response_payload.get("payload", {}) if response_payload else {}
        )
        if payload:
            coordinates = self.toolkit.extract_coordinate_pair(
                payload, payload_snapshot
            )
            if coordinates:
                return coordinates
            coordinates = self.toolkit.extract_coordinate_pair(
                payload, payload.model_dump()
            )
            if coordinates:
                return coordinates
        lon_candidate = fallback.get("longitude")
        lat_candidate = fallback.get("latitude")
        if lon_candidate is None or lat_candidate is None:
            return None
        try:
            lon_value = float(lon_candidate)
            lat_value = float(lat_candidate)
        except TypeError, ValueError:
            return None
        return lon_value, lat_value

    def _coerce_coordinate_scalar(self, value: Any) -> float | None:
        if isinstance(value, (int, float)):
            return float(value)
        return None

    def format_coordinate_pair(self, coordinates: CoordinatePair | None) -> str | None:
        if coordinates is None:
            return None
        lon, lat = coordinates
        return json.dumps({"longitude": lon, "latitude": lat})

    def build_search_session_record(
        self,
        *,
        payload: LocationSearchRequest | None,
        response_payload: dict[str, Any] | None,
        fallback: dict[str, Any],
        state: str,
    ) -> dict[str, Any]:
        return self.orchestrator.build_search_session_record(
            payload=payload,
            response_payload=response_payload,
            fallback=fallback,
            state=state,
        )

    async def build_map_session(
        self,
        *,
        payload: LocationSearchRequest,
        search_payload: dict[str, Any],
        satellite_payload: dict[str, Any],
    ) -> dict[str, Any]:
        return await self.orchestrator.assemble_map_session(
            payload=payload,
            search_payload=search_payload,
            satellite_payload=satellite_payload,
        )

    async def record_search_session(
        self,
        *,
        payload: LocationSearchRequest | None,
        response_payload: dict[str, Any] | None,
        fallback: dict[str, Any],
        state: str,
    ) -> None:
        record = self.build_search_session_record(
            payload=payload,
            response_payload=response_payload,
            fallback=fallback,
            state=state,
        )
        try:
            await asyncio.to_thread(self.serializer.insert_search_session, record)
        except Exception as exc:
            logger.warning("Failed to store search session: %s", exc)

    async def get_location_coordinates(
        self, payload: LocationSearchRequest
    ) -> dict[str, object]:
        return await self.orchestrator.resolve_coordinates(payload)

    async def process_location_search(
        self, payload: LocationSearchRequest
    ) -> dict[str, Any]:
        return await self.orchestrator.execute(payload)

    async def process_location_search_job(
        self,
        *,
        payload: LocationSearchRequest,
        request_context: dict[str, Any],
        job_id: str,
    ) -> dict[str, Any]:
        response_payload: dict[str, Any] | None = None
        try:
            self.job_manager.update_progress(
                job_id, MAP_SEARCH_JOB_PROGRESS_COORDINATES
            )
            search_payload = await self.get_location_coordinates(payload)
            if self.job_manager.should_stop(job_id):
                await self.record_search_session(
                    payload=payload,
                    response_payload=response_payload,
                    fallback=request_context,
                    state=JOB_STATUS_CANCELLED,
                )
                return {}
            self.job_manager.update_progress(job_id, MAP_SEARCH_JOB_PROGRESS_IMAGERY)

            try:
                satellite_payload = await self.renderer.build_satellite_payload(
                    payload, search_payload
                )
            except (GIBSValidationError, MapValidationError, LayerProviderError) as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=str(exc),
                ) from exc
            except (GIBSRequestError, MapRequestError) as exc:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=str(exc),
                ) from exc

            search_payload["satellite_imagery"] = satellite_payload
            map_session = await self.build_map_session(
                payload=payload,
                search_payload=search_payload,
                satellite_payload=satellite_payload,
            )
            search_payload["map_session"] = map_session
            search_payload["compliance_warnings"] = map_session.get(
                "compliance_warnings", []
            )
            self.job_manager.update_progress(
                job_id, MAP_SEARCH_JOB_PROGRESS_POSTPROCESS
            )

            lat_value = self._coerce_coordinate_scalar(search_payload.get("latitude"))
            lon_value = self._coerce_coordinate_scalar(search_payload.get("longitude"))
            if lat_value is not None and lon_value is not None:
                try:
                    elevation_data = await self.elevation_service.get_elevation(
                        lat_value, lon_value
                    )
                    search_payload["elevation"] = elevation_data
                except Exception as exc:
                    logger.warning("Failed to fetch elevation: %s", exc)
                    search_payload["elevation"] = None

            response_payload = build_search_response(
                search_payload=search_payload,
                map_session=map_session,
            )
            self.job_manager.update_result(job_id, response_payload)
            if self.job_manager.should_stop(job_id):
                await self.record_search_session(
                    payload=payload,
                    response_payload=response_payload,
                    fallback=request_context,
                    state=JOB_STATUS_CANCELLED,
                )
                return response_payload
            await self.record_search_session(
                payload=payload,
                response_payload=response_payload,
                fallback=request_context,
                state="success",
            )
            self.job_manager.update_progress(job_id, MAP_SEARCH_JOB_PROGRESS_PERSISTED)
            return response_payload
        except HTTPException as exc:
            await self.record_search_session(
                payload=payload,
                response_payload=response_payload,
                fallback=request_context,
                state="failed",
            )
            message = str(exc.detail) if exc.detail is not None else str(exc)
            raise RuntimeError(message) from exc
        except Exception:
            await self.record_search_session(
                payload=payload,
                response_payload=response_payload,
                fallback=request_context,
                state="failed",
            )
            raise

    async def search_by_location(
        self,
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
    ) -> SearchByLocationResponse:
        payload: LocationSearchRequest | None = None
        response_payload: dict[str, Any] | None = None
        request_context = build_request_context(
            country=country,
            city=city,
            address=address,
            longitude=longitude,
            latitude=latitude,
            geospatial_layers=geospatial_layers,
            overlay_ids=overlay_ids,
            basemap_id=basemap_id,
            map_tiles=map_tiles,
        )
        try:
            payload_data = build_location_search_payload_data(
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
                map_tiles=request_context["map_tiles"],
                image_crs=image_crs,
                image_format=image_format,
            )
            payload = await asyncio.to_thread(
                LocationSearchRequest.model_validate, payload_data
            )
            response_payload = await self.process_location_search(payload)
            typed_response = await asyncio.to_thread(
                SearchByLocationResponse.model_validate, response_payload
            )
            await self.record_search_session(
                payload=payload,
                response_payload=response_payload,
                fallback=request_context,
                state="success",
            )
            return typed_response
        except ValidationError as exc:
            await self.record_search_session(
                payload=payload,
                response_payload=response_payload,
                fallback=request_context,
                state="failed",
            )
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=sanitize_validation_errors(exc.errors()),
            ) from exc
        except Exception:
            await self.record_search_session(
                payload=payload,
                response_payload=response_payload,
                fallback=request_context,
                state="failed",
            )
            raise

    async def start_search_job(
        self,
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
    ) -> JobStartResponse:
        payload: LocationSearchRequest | None = None
        response_payload: dict[str, Any] | None = None
        request_context = build_request_context(
            country=country,
            city=city,
            address=address,
            longitude=longitude,
            latitude=latitude,
            geospatial_layers=geospatial_layers,
            overlay_ids=overlay_ids,
            basemap_id=basemap_id,
            map_tiles=map_tiles,
        )
        try:
            payload_data = build_location_search_payload_data(
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
                map_tiles=request_context["map_tiles"],
                image_crs=image_crs,
                image_format=image_format,
            )
            payload = await asyncio.to_thread(
                LocationSearchRequest.model_validate, payload_data
            )
        except ValidationError as exc:
            await self.record_search_session(
                payload=payload,
                response_payload=response_payload,
                fallback=request_context,
                state="failed",
            )
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=sanitize_validation_errors(exc.errors()),
            ) from exc

        job_id = self.job_manager.start_job(
            job_type="map_search",
            runner=run_map_search_job,
            kwargs={
                "service": self,
                "payload": payload,
                "request_context": request_context,
            },
        )
        job_status = self.job_manager.get_job_status(job_id)
        if job_status is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=MAP_SEARCH_JOB_INIT_ERROR,
            )
        return JobStartResponse(
            job_id=job_id,
            job_type=job_status["job_type"],
            status=job_status["status"],
            message=MAP_SEARCH_JOB_START_MESSAGE,
            poll_interval=get_server_settings().jobs.polling_interval,
        )

    async def get_search_job_status(self, job_id: str) -> JobStatusResponse:
        job_status = self.job_manager.get_job_status(job_id)
        if job_status is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job not found: {job_id}",
            )
        return JobStatusResponse(**job_status)

    async def cancel_search_job(self, job_id: str) -> JobCancelResponse:
        job_status = self.job_manager.get_job_status(job_id)
        if job_status is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job not found: {job_id}",
            )
        success = self.job_manager.cancel_job(job_id)
        return JobCancelResponse(
            job_id=job_id,
            success=success,
            message=(
                MAP_SEARCH_CANCELLATION_REQUESTED
                if success
                else MAP_SEARCH_CANCELLATION_NOT_ALLOWED
            ),
        )

    async def get_catalog(self) -> GeospatialCatalogResponse:
        catalog = await asyncio.to_thread(self.catalog_service.list_catalog)
        return GeospatialCatalogResponse.model_validate(catalog)
