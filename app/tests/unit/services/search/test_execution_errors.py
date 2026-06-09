from __future__ import annotations

from server.services.geospatial.osm_tiles import OsmTileProxyError
from server.services.search.composition import build_search_runtime
from server.services.search.errors import MapSearchTileProxyError


class _FailingProxyService:
    def fetch_tile(self, z: int, x: int, y: int):  # noqa: ANN001, ARG002
        raise OsmTileProxyError("OSM basemap tile provider is unavailable.")


def test_fetch_osm_basemap_tile_propagates_wrapped_errors() -> None:
    runtime = build_search_runtime()
    runtime.search_execution.osm_tile_proxy_service = _FailingProxyService()  # type: ignore[assignment]

    try:
        runtime.search_execution.fetch_osm_basemap_tile(1, 1, 1)
    except MapSearchTileProxyError as exc:
        assert "unavailable" in str(exc)
    else:
        raise AssertionError("Expected MapSearchTileProxyError")
