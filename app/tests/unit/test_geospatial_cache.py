from __future__ import annotations

from server.services.geospatial.cache import (
    CacheLookupStatus,
    GeospatialCache,
    cache_key_for_request,
)
from server.services.geospatial.providers.base import ProviderRequest


class _Clock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


def test_geospatial_cache_returns_hit_stale_then_miss() -> None:
    clock = _Clock()
    cache = GeospatialCache(clock=clock)

    cache.set("rainviewer:metadata", {"frame": 1}, ttl_seconds=10, stale_while_revalidate_seconds=5)

    assert cache.get("rainviewer:metadata").status == CacheLookupStatus.HIT
    clock.value = 11.0
    stale = cache.get("rainviewer:metadata")
    assert stale.status == CacheLookupStatus.STALE
    assert stale.value == {"frame": 1}
    clock.value = 16.0
    assert cache.get("rainviewer:metadata").status == CacheLookupStatus.MISS


def test_geospatial_cache_can_invalidate_entries() -> None:
    cache = GeospatialCache()

    cache.set("openaq:stations", [1, 2], ttl_seconds=60)
    cache.invalidate("openaq:stations")

    assert cache.get("openaq:stations").status == CacheLookupStatus.MISS


def test_geospatial_cache_key_for_request_excludes_raw_credentials() -> None:
    key = cache_key_for_request(
        "openaq",
        ProviderRequest(
            capability_id="openaq_air_quality",
            bbox=(1, 2, 3, 4),
            zoom=9,
            params={"api_key": "raw-secret", "pollutant": "pm25"},
        ),
    )

    assert "raw-secret" not in key
    assert key.startswith("openaq:openaq_air_quality:")
