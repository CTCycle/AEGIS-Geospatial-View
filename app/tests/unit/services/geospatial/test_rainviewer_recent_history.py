from __future__ import annotations

import asyncio
from typing import Any

from server.services.geospatial.rainviewer import RainViewerService


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
