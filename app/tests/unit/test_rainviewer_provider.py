from __future__ import annotations

import asyncio

from server.services.geospatial.cache import GeospatialCache
from server.services.geospatial.providers.base import ProviderRequest
from server.services.geospatial.providers.rainviewer import RainViewerProvider
from server.services.geospatial.rainviewer import RainViewerRequestError


###############################################################################
class _Clock:

    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        self.value = 0.0

    # -------------------------------------------------------------------------
    def __call__(self) -> float:
        return self.value


###############################################################################
class _RainViewerService:

    # -------------------------------------------------------------------------
    def __init__(
        self, payload: dict[str, object] | None = None, *, fail: bool = False
    ) -> None:
        self.payload = payload or {
            "tile_url_template": "https://tiles.test/{z}/{x}/{y}.png",
            "latest_time": 123,
            "frame_count": 2,
            "resolved_at": "2026-05-11T00:00:00+00:00",
            "attribution": "RainViewer",
        }
        self.fail = fail
        self.calls = 0

    # -------------------------------------------------------------------------
    async def get_latest_radar_metadata(self) -> dict[str, object]:
        self.calls += 1
        if self.fail:
            raise RainViewerRequestError("offline")
        return self.payload


###############################################################################
def test_rainviewer_provider_returns_resolved_raster_tile_payload() -> None:
    service = _RainViewerService()
    provider = RainViewerProvider(service=service)  # type: ignore[arg-type]

    response = asyncio.run(
        provider.fetch(ProviderRequest(capability_id="rainviewer_precipitation_radar"))
    )

    assert response.provider_id == "rainviewer"
    assert response.payload["renderingMode"] == "raster-tile"
    assert response.payload["tileUrl"] == "https://tiles.test/{z}/{x}/{y}.png"
    assert response.stale is False


###############################################################################
def test_rainviewer_provider_uses_stale_cache_when_refresh_fails() -> None:
    clock = _Clock()
    cache = GeospatialCache(clock=clock)
    cache.set(
        "rainviewer:latest-radar",
        {
            "tile_url_template": "https://stale.test/{z}/{x}/{y}.png",
            "latest_time": 100,
            "frame_count": 1,
            "attribution": "RainViewer",
        },
        ttl_seconds=1,
        stale_while_revalidate_seconds=10,
    )
    clock.value = 2.0
    provider = RainViewerProvider(
        service=_RainViewerService(fail=True),  # type: ignore[arg-type]
        cache=cache,
    )

    response = asyncio.run(
        provider.fetch(ProviderRequest(capability_id="rainviewer_precipitation_radar"))
    )

    assert response.stale is True
    assert response.payload["tileUrl"] == "https://stale.test/{z}/{x}/{y}.png"
    assert response.warnings


###############################################################################
def test_rainviewer_provider_returns_empty_state_when_no_cache_exists() -> None:
    provider = RainViewerProvider(service=_RainViewerService(fail=True))  # type: ignore[arg-type]

    response = asyncio.run(
        provider.fetch(ProviderRequest(capability_id="rainviewer_precipitation_radar"))
    )

    assert response.payload["status"] == "empty"
    assert response.payload["tileUrl"] is None
    assert response.warnings


###############################################################################
def test_rainviewer_provider_returns_empty_state_for_malformed_payload() -> None:
    provider = RainViewerProvider(
        service=_RainViewerService(payload={"latest_time": 123}),  # type: ignore[arg-type]
    )

    response = asyncio.run(
        provider.fetch(ProviderRequest(capability_id="rainviewer_precipitation_radar"))
    )

    assert response.payload["status"] == "empty"
    assert response.payload["frameCount"] == 0
    assert "usable radar tile frame" in response.warnings[0]


###############################################################################
def test_rainviewer_provider_uses_stale_cache_when_payload_is_malformed() -> None:
    clock = _Clock()
    cache = GeospatialCache(clock=clock)
    cache.set(
        "rainviewer:latest-radar",
        {
            "tile_url_template": "https://stale.test/{z}/{x}/{y}.png",
            "latest_time": 100,
            "frame_count": 1,
            "attribution": "RainViewer",
        },
        ttl_seconds=1,
        stale_while_revalidate_seconds=10,
    )
    clock.value = 2.0
    provider = RainViewerProvider(
        service=_RainViewerService(payload={"tile_url_template": ""}),  # type: ignore[arg-type]
        cache=cache,
    )

    response = asyncio.run(
        provider.fetch(ProviderRequest(capability_id="rainviewer_precipitation_radar"))
    )

    assert response.stale is True
    assert response.payload["tileUrl"] == "https://stale.test/{z}/{x}/{y}.png"


###############################################################################
def test_rainviewer_provider_caches_successful_metadata_for_five_minutes() -> None:
    service = _RainViewerService()
    provider = RainViewerProvider(service=service)  # type: ignore[arg-type]
    request = ProviderRequest(capability_id="rainviewer_precipitation_radar")

    first = asyncio.run(provider.fetch(request))
    second = asyncio.run(provider.fetch(request))

    assert first.payload == second.payload
    assert service.calls == 1


###############################################################################
def test_rainviewer_provider_handles_timeout_like_service_failure() -> None:

    ###############################################################################
    class _TimeoutService:

        # -------------------------------------------------------------------------
        async def get_latest_radar_metadata(self) -> dict[str, object]:
            raise RainViewerRequestError("timed out")

    provider = RainViewerProvider(service=_TimeoutService())  # type: ignore[arg-type]

    response = asyncio.run(
        provider.fetch(ProviderRequest(capability_id="rainviewer_precipitation_radar"))
    )

    assert response.payload["status"] == "empty"
    assert "timed out" in response.warnings[0]
