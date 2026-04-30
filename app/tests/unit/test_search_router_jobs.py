from __future__ import annotations

import asyncio

from server.api.search import router
from server.domain.agent.decision import ResolvedLocation
from server.domain.geographics import LocationSearchRequest
from server.domain.jobs import (
    JobCancelResponse,
    JobStartResponse,
    JobStatusResponse,
)
from server.services.search.composition import build_search_runtime


def _location_search_request() -> LocationSearchRequest:
    return LocationSearchRequest(
        resolved_location=ResolvedLocation(
            label="Rome, Italy",
            latitude=41.9,
            longitude=12.5,
            city="Rome",
            country="Italy",
        ),
        intent_id="air_quality",
        time_mode="current",
        basemap_id="osm_default",
        overlay_ids=["openaq_air_quality"],
        viewport={
            "center_latitude": 41.9,
            "center_longitude": 12.5,
            "radius_m": 2500.0,
        },
    )


def test_jobs_router_wiring_and_response_models() -> None:
    route_map = {
        (route.path, tuple(sorted(route.methods or []))): route
        for route in router.routes
    }
    assert ("/maps/jobs", ("POST",)) in route_map
    assert ("/maps/jobs/{job_id}", ("GET",)) in route_map
    assert ("/maps/jobs/{job_id}", ("DELETE",)) in route_map

    assert route_map[("/maps/jobs", ("POST",))].response_model is JobStartResponse
    assert (
        route_map[("/maps/jobs/{job_id}", ("GET",))].response_model is JobStatusResponse
    )
    assert (
        route_map[("/maps/jobs/{job_id}", ("DELETE",))].response_model
        is JobCancelResponse
    )


def test_search_job_start_status_cancel_shapes(monkeypatch) -> None:
    runtime = build_search_runtime()
    monkeypatch.setattr(runtime.job_manager, "start_job", lambda **kwargs: "job-1")
    monkeypatch.setattr(
        runtime.job_manager,
        "get_job_status",
        lambda job_id: {
            "job_id": job_id,
            "job_type": "map_search",
            "status": "running",
            "progress": 20.0,
            "result": None,
            "error": None,
        },
    )
    monkeypatch.setattr(runtime.job_manager, "cancel_job", lambda job_id: True)

    started = asyncio.run(
        runtime.search_execution.start_search_job(_location_search_request())
    )
    assert isinstance(started, JobStartResponse)
    assert started.job_id == "job-1"

    status = asyncio.run(runtime.search_execution.get_search_job_status("job-1"))
    assert isinstance(status, JobStatusResponse)
    assert status.job_id == "job-1"

    cancel = asyncio.run(runtime.search_execution.cancel_search_job("job-1"))
    assert isinstance(cancel, JobCancelResponse)
    assert cancel.success is True


def test_cancellation_path_consistency(monkeypatch) -> None:
    runtime = build_search_runtime()
    monkeypatch.setattr(
        runtime.job_manager,
        "get_job_status",
        lambda job_id: {
            "job_id": job_id,
            "job_type": "map_search",
            "status": "completed",
            "progress": 100.0,
            "result": {},
            "error": None,
        },
    )
    monkeypatch.setattr(runtime.job_manager, "cancel_job", lambda job_id: False)
    cancel = asyncio.run(runtime.search_execution.cancel_search_job("job-2"))
    assert cancel.job_id == "job-2"
    assert cancel.success is False
