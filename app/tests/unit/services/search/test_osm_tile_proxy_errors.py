from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.api.search import get_search_execution, router
from server.services.geospatial.osm_tiles import OsmTileProxyError
from server.services.search.errors import MapSearchTileProxyError
from server.services.search.execution import MapSearchExecutionService


class _FailingProxyService:
    def fetch_tile(self, z: int, x: int, y: int) -> tuple[bytes, str, str]:  # noqa: ARG002
        raise OsmTileProxyError("OSM basemap tile provider is unavailable.")


def test_execution_wraps_osm_proxy_failures() -> None:
    service = MapSearchExecutionService(
        orchestrator=object(),  # type: ignore[arg-type]
        catalog_service=object(),  # type: ignore[arg-type]
        osm_tile_proxy_service=_FailingProxyService(),  # type: ignore[arg-type]
    )
    try:
        service.fetch_osm_basemap_tile(1, 1, 1)
    except MapSearchTileProxyError as exc:
        assert "OSM basemap tile provider is unavailable." in str(exc)
    else:
        raise AssertionError("Expected MapSearchTileProxyError")


def test_endpoint_returns_502_text_plain_for_tile_proxy_failures() -> None:
    app = FastAPI()
    app.include_router(router)

    class _ExecutionStub:
        def fetch_osm_basemap_tile(self, z: int, x: int, y: int) -> tuple[bytes, str, str]:  # noqa: ARG002
            raise MapSearchTileProxyError("OSM basemap tile provider is unavailable.")

    app.dependency_overrides[get_search_execution] = lambda: _ExecutionStub()
    client = TestClient(app)
    response = client.get("/maps/basemaps/osm/1/1/1.png")
    assert response.status_code == 502
    assert response.headers["content-type"].startswith("text/plain")
    assert "unavailable" in response.text
