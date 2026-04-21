from __future__ import annotations

from fastapi import HTTPException, status

from AEGIS.server.configurations import get_server_settings
from AEGIS.server.domain.geographics import (
    GeospatialCatalogResponse,
    LocationSearchRequest,
    SearchByLocationResponse,
)
from AEGIS.server.domain.jobs import JobCancelResponse, JobStartResponse, JobStatusResponse
from AEGIS.server.services.geospatial.catalog import GeospatialCatalogService
from AEGIS.server.services.jobs import JobManager
from AEGIS.server.services.search.orchestrator import LocationSearchOrchestrator
from AEGIS.server.common.constants import (
    MAP_SEARCH_CANCELLATION_NOT_ALLOWED,
    MAP_SEARCH_CANCELLATION_REQUESTED,
    MAP_SEARCH_JOB_INIT_ERROR,
    MAP_SEARCH_JOB_START_MESSAGE,
    MAP_SEARCH_STATUS_MESSAGE,
)


class MapSearchExecutionService:
    def __init__(
        self,
        *,
        orchestrator: LocationSearchOrchestrator,
        catalog_service: GeospatialCatalogService,
        job_manager: JobManager,
    ) -> None:
        self.orchestrator = orchestrator
        self.catalog_service = catalog_service
        self.job_manager = job_manager

    async def search_by_location(self, payload: LocationSearchRequest) -> SearchByLocationResponse:
        map_session = await self.orchestrator.execute(payload)
        return SearchByLocationResponse(
            status_message=MAP_SEARCH_STATUS_MESSAGE,
            map_session=map_session,
        )

    async def start_search_job(self, payload: LocationSearchRequest) -> JobStartResponse:
        async def _runner() -> dict[str, object]:
            response = await self.search_by_location(payload)
            return response.model_dump(mode="json")

        def _sync_runner(service: "MapSearchExecutionService", job_payload: LocationSearchRequest) -> dict[str, object]:
            import asyncio

            return asyncio.run(service.search_by_location(job_payload)).model_dump(mode="json")

        job_id = self.job_manager.start_job(
            job_type="map_search",
            runner=_sync_runner,
            kwargs={"service": self, "job_payload": payload},
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
        catalog = self.catalog_service.list_catalog()
        return GeospatialCatalogResponse.model_validate(catalog)
