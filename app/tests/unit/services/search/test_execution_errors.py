from __future__ import annotations

import asyncio

import pytest

from server.common.constants import MAP_SEARCH_JOB_INIT_ERROR
from server.domain.agent.decision import ResolvedLocation
from server.domain.geographics import LocationSearchRequest
from server.services.search.composition import build_search_runtime
from server.services.search.errors import (
    MapSearchJobInitializationError,
    MapSearchJobNotFoundError,
)


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


def test_start_search_job_raises_initialization_error_when_status_missing(monkeypatch) -> None:
    runtime = build_search_runtime()
    monkeypatch.setattr(runtime.job_manager, "start_job", lambda **kwargs: "job-1")
    monkeypatch.setattr(runtime.job_manager, "get_job_status", lambda job_id: None)

    with pytest.raises(MapSearchJobInitializationError, match=MAP_SEARCH_JOB_INIT_ERROR):
        asyncio.run(runtime.search_execution.start_search_job(_location_search_request()))


def test_get_search_job_status_raises_not_found_for_missing_job(monkeypatch) -> None:
    runtime = build_search_runtime()
    monkeypatch.setattr(runtime.job_manager, "get_job_status", lambda job_id: None)

    with pytest.raises(MapSearchJobNotFoundError, match="Job not found: missing"):
        asyncio.run(runtime.search_execution.get_search_job_status("missing"))


def test_cancel_search_job_raises_not_found_for_missing_job(monkeypatch) -> None:
    runtime = build_search_runtime()
    monkeypatch.setattr(runtime.job_manager, "get_job_status", lambda job_id: None)

    with pytest.raises(MapSearchJobNotFoundError, match="Job not found: missing"):
        asyncio.run(runtime.search_execution.cancel_search_job("missing"))
