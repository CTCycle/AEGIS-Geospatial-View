from __future__ import annotations

import pytest
from fastapi import HTTPException, FastAPI
from fastapi.testclient import TestClient

from server.api.search import raise_map_search_http_error, router
from server.services.search.errors import (
    MapSearchExecutionError,
    MapSearchJobInitializationError,
    MapSearchJobNotFoundError,
)


###############################################################################
class _FakeJobService:

    # -------------------------------------------------------------------------
    def create_map_job(self, payload):  # noqa: ANN001
        _ = payload
        raise_map_search_http_error(MapSearchJobInitializationError("init failed"))

    # -------------------------------------------------------------------------
    def get_job(self, job_id: str):
        _ = job_id
        return None

    # -------------------------------------------------------------------------
    def cancel_job(self, job_id: str):
        _ = job_id
        return None


###############################################################################
class _FakeSearchExecution:

    # -------------------------------------------------------------------------
    async def search_by_location(self, payload):  # noqa: ANN001
        return payload

    # -------------------------------------------------------------------------
    async def get_catalog(self):
        return {"categories": [], "capabilities": []}

    # -------------------------------------------------------------------------
    def fetch_osm_basemap_tile(self, z: int, x: int, y: int):
        return b"", "image/png", "max-age=60"


###############################################################################
def _build_client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.state.search_runtime = type("RuntimeHolder", (), {"search_execution": _FakeSearchExecution()})()
    app.state.job_service = _FakeJobService()
    return TestClient(app)


###############################################################################
def test_get_map_job_endpoint_maps_not_found_to_http_404() -> None:
    client = _build_client()
    response = client.get("/api/maps/jobs/missing")
    assert response.status_code == 404
    assert response.json()["detail"] == "Job not found: missing"


###############################################################################
def test_delete_map_job_endpoint_maps_not_found_to_http_404() -> None:
    client = _build_client()
    response = client.delete("/api/maps/jobs/missing")
    assert response.status_code == 404
    assert response.json()["detail"] == "Job not found: missing"


###############################################################################
@pytest.mark.parametrize(
    ("error", "expected_status", "expected_detail"),
    [
        (MapSearchJobNotFoundError("Job not found: missing"), 404, "Job not found: missing"),
        (MapSearchJobInitializationError("init failed"), 500, "init failed"),
        (MapSearchExecutionError("generic failure"), 500, "generic failure"),
    ],
)
def test_raise_map_search_http_error_maps_expected_statuses(
    error: MapSearchExecutionError,
    expected_status: int,
    expected_detail: str,
) -> None:
    with pytest.raises(HTTPException) as exc_info:
        raise_map_search_http_error(error)

    assert exc_info.value.status_code == expected_status
    assert exc_info.value.detail == expected_detail
