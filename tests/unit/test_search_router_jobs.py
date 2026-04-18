from __future__ import annotations
import asyncio

from AEGIS.server.api import search
from AEGIS.server.domain.jobs import (
    JobCancelResponse,
    JobStartResponse,
    JobStatusResponse,
)


def test_jobs_router_wiring_and_response_models() -> None:
    route_map = {
        (route.path, tuple(sorted(route.methods or []))): route
        for route in search.router.routes
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
    monkeypatch.setattr(search.job_manager, "start_job", lambda **kwargs: "job-1")
    monkeypatch.setattr(
        search.job_manager,
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
    monkeypatch.setattr(search.job_manager, "cancel_job", lambda job_id: True)

    started = asyncio.run(
        search.search_execution.start_search_job(
            datetime_value="2024-06-15T12:00:00",
            time_of_day=None,
            timeline_year=None,
            country=None,
            city=None,
            address=None,
            use_coordinates=True,
            latitude=41.9,
            longitude=12.5,
            geospatial_layers=[],
            basemap_id=None,
            overlay_ids=[],
            aoi=None,
            commute=None,
            bbox=None,
            radius_m=None,
            map_size_m=None,
            map_tiles=None,
            image_width=None,
            image_height=None,
            image_crs=None,
            image_format=None,
        )
    )
    assert isinstance(started, JobStartResponse)
    assert started.job_id == "job-1"

    status = asyncio.run(search.search_execution.get_search_job_status("job-1"))
    assert isinstance(status, JobStatusResponse)
    assert status.job_id == "job-1"

    cancel = asyncio.run(search.search_execution.cancel_search_job("job-1"))
    assert isinstance(cancel, JobCancelResponse)
    assert cancel.success is True


def test_cancellation_path_consistency(monkeypatch) -> None:
    monkeypatch.setattr(
        search.job_manager,
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
    monkeypatch.setattr(search.job_manager, "cancel_job", lambda job_id: False)
    cancel = asyncio.run(search.search_execution.cancel_search_job("job-2"))
    assert cancel.job_id == "job-2"
    assert cancel.success is False
