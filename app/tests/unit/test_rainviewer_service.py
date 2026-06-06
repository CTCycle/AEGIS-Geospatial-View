from __future__ import annotations

import asyncio

from server.services.geospatial.rainviewer import RainViewerRequestError, RainViewerService


def test_rainviewer_service_returns_cached_metadata_without_refetch() -> None:
    calls: list[str] = []

    async def _fetcher(url: str, headers: dict[str, str] | None = None) -> dict[str, object]:
        calls.append(url)
        _ = headers
        return {
            "host": "https://tilecache.rainviewer.com",
            "radar": {
                "past": [
                    {"time": 100, "path": "/v2/radar/100"},
                    {"time": 200, "path": "/v2/radar/200"},
                ]
            },
        }

    service = RainViewerService(fetcher=_fetcher, cache_ttl_s=300.0)

    first = asyncio.run(service.get_latest_radar_metadata())
    second = asyncio.run(service.get_latest_radar_metadata())

    assert first["latest_time"] == 200
    assert first["tile_url_template"] == "https://tilecache.rainviewer.com/v2/radar/200/256/{z}/{x}/{y}/2/1_1.png"
    assert second["latest_time"] == 200
    assert calls == ["https://api.rainviewer.com/public/weather-maps.json"]


def test_rainviewer_service_rejects_malformed_payload() -> None:
    async def _fetcher(url: str, headers: dict[str, str] | None = None) -> dict[str, object]:
        _ = url, headers
        return {"host": "https://tilecache.rainviewer.com", "radar": {"past": []}}

    service = RainViewerService(fetcher=_fetcher)

    try:
        asyncio.run(service.get_latest_radar_metadata())
    except RainViewerRequestError as exc:
        assert "did not return radar frames" in str(exc)
    else:
        raise AssertionError("RainViewerRequestError was not raised.")
