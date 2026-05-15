from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.api.search import router
from server.common.constants import MAP_SEARCH_JOB_INIT_ERROR
from server.services.search.errors import (
    MapSearchJobInitializationError,
    MapSearchJobNotFoundError,
)


class _FakeSearchExecution:
    async def search_by_location(self, payload):  # noqa: ANN001
        return payload

    async def start_search_job(self, payload):  # noqa: ANN001
        raise MapSearchJobInitializationError(MAP_SEARCH_JOB_INIT_ERROR)

    async def get_search_job_status(self, job_id: str):
        raise MapSearchJobNotFoundError(f"Job not found: {job_id}")

    async def cancel_search_job(self, job_id: str):
        raise MapSearchJobNotFoundError(f"Job not found: {job_id}")

    async def get_catalog(self):
        return {"categories": [], "capabilities": []}

    def fetch_osm_basemap_tile(self, z: int, x: int, y: int):
        return b"", "image/png", "max-age=60"


class _RuntimeHolder:
    pass


def _build_client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.state.search_runtime = _RuntimeHolder()
    app.state.search_runtime.search_execution = _FakeSearchExecution()
    return TestClient(app)


def test_get_map_job_endpoint_maps_not_found_to_http_404() -> None:
    client = _build_client()

    response = client.get("/api/maps/jobs/missing")

    assert response.status_code == 404
    assert response.json()["detail"] == "Job not found: missing"


def test_delete_map_job_endpoint_maps_not_found_to_http_404() -> None:
    client = _build_client()

    response = client.delete("/api/maps/jobs/missing")

    assert response.status_code == 404
    assert response.json()["detail"] == "Job not found: missing"


def test_post_map_jobs_endpoint_maps_initialization_error_to_http_500() -> None:
    client = _build_client()

    response = client.post(
        "/api/maps/jobs",
        json={
            "resolved_location": {
                "label": "Rome, Italy",
                "latitude": 41.9,
                "longitude": 12.5,
            },
            "intent_id": "air_quality",
            "time_mode": "current",
            "basemap_id": "osm_default",
            "overlay_ids": ["openaq_air_quality"],
            "viewport": {
                "center_latitude": 41.9,
                "center_longitude": 12.5,
                "radius_m": 2500.0,
            },
        },
    )

    assert response.status_code == 500
    assert response.json()["detail"] == MAP_SEARCH_JOB_INIT_ERROR
