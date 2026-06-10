from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from server.common.paths import (
    JOBS_JOB_CANCEL_ROUTE,
    JOBS_JOB_EVENTS_ROUTE,
    JOBS_JOB_ROUTE,
    JOBS_ROUTER_PREFIX,
)
from server.domain.jobs import (
    BackgroundJobEventsResponse,
    BackgroundJobStatusResponse,
    JobCancelResponse,
)
from server.services.jobs import BackgroundJobService

router = APIRouter(prefix=JOBS_ROUTER_PREFIX, tags=["jobs"])


###############################################################################
def get_job_service(request: Request) -> BackgroundJobService:
    return request.app.state.job_service


###############################################################################
@router.get(JOBS_JOB_ROUTE, response_model=BackgroundJobStatusResponse, status_code=status.HTTP_200_OK)
async def get_job(
    job_id: str,
    job_service: BackgroundJobService = Depends(get_job_service),
) -> BackgroundJobStatusResponse:
    job = job_service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job not found: {job_id}")
    return job


###############################################################################
@router.get(
    JOBS_JOB_EVENTS_ROUTE,
    response_model=BackgroundJobEventsResponse,
    status_code=status.HTTP_200_OK,
)
async def get_job_events(
    job_id: str,
    job_service: BackgroundJobService = Depends(get_job_service),
) -> BackgroundJobEventsResponse:
    events = job_service.list_events(job_id)
    if events is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job not found: {job_id}")
    return events


###############################################################################
@router.post(
    JOBS_JOB_CANCEL_ROUTE,
    response_model=JobCancelResponse,
    status_code=status.HTTP_200_OK,
)
async def cancel_job(
    job_id: str,
    job_service: BackgroundJobService = Depends(get_job_service),
) -> JobCancelResponse:
    response = job_service.cancel_job(job_id)
    if response is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job not found: {job_id}")
    return response
