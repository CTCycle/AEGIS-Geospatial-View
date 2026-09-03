from __future__ import annotations

import asyncio
from typing import Any

from server.services.geospatial.rainviewer import (
    RainViewerRequestError,
    RainViewerService,
)


###############################################################################
def test_rainviewer_ignores_discontinued_nowcast_frames() -> None:
    async def fetcher(_url: str, _headers: dict[str, str]) -> dict[str, Any]:
        return {
            "host": "https://tilecache.rainviewer.com",
            "radar": {
                "past": [
                    {"time": 100, "path": "/v2/radar/100"},
                    {"time": 200, "path": "/v2/radar/200"},
                ],
                "nowcast": [
                    {"time": 999, "path": "/v2/radar/999"},
                ],
            },
        }

    service = RainViewerService(
        metadata_url="https://example.test/weather-maps.json",
        user_agent="AEGIS-Test/1.0",
        timeout_s=1.0,
        cache_ttl_s=30.0,
        min_call_interval_s=0.05,
        fetcher=fetcher,
    )

    result = asyncio.run(service.get_latest_radar_metadata())

    assert result["kind"] == "recent_precipitation_radar"
    assert result["latest_time"] == 200
    assert result["history_start_time"] == 100
    assert result["history_end_time"] == 200
    assert result["frame_count"] == 2
    assert result["max_zoom"] == 7
    assert "/v2/radar/200/256/" in result["tile_url_template"]
    assert "/v2/radar/999/" not in result["tile_url_template"]


def test_rainviewer_filters_malformed_past_timestamps() -> None:
    async def fetcher(_url: str, _headers: dict[str, str]) -> dict[str, Any]:
        return {
            "radar": {
                "past": [
                    {"time": "not-a-timestamp", "path": "/v2/radar/bad"},
                    {"time": None, "path": "/v2/radar/missing"},
                    {"time": 300, "path": "/v2/radar/300"},
                ]
            }
        }

    service = RainViewerService(fetcher=fetcher)

    result = asyncio.run(service.get_latest_radar_metadata())

    assert result["latest_time"] == 300
    assert result["frame_count"] == 1
    assert result["history_start_time"] == 300


def test_rainviewer_rejects_when_no_past_frame_has_a_valid_timestamp() -> None:
    async def fetcher(_url: str, _headers: dict[str, str]) -> dict[str, Any]:
        return {
            "radar": {
                "past": [
                    {"time": "invalid", "path": "/v2/radar/invalid"},
                    {"time": 0, "path": "/v2/radar/zero"},
                ]
            }
        }

    service = RainViewerService(fetcher=fetcher)

    try:
        asyncio.run(service.get_latest_radar_metadata())
    except RainViewerRequestError as exc:
        assert "recent radar history frames" in str(exc)
    else:
        raise AssertionError("RainViewerRequestError was not raised.")
