from __future__ import annotations

from tests.conftest import run_async_in_thread

import pytest

from server.services.geospatial.cache import GeospatialCache
from server.services.geospatial.providers.base import (
    ProviderAuthError,
    ProviderRequest,
    ProviderUnavailableError,
)
from server.services.geospatial.providers.openchargemap import OpenChargeMapProvider
from server.services.geospatial.providers.opentripmap import OpenTripMapProvider
from server.services.geospatial.providers.ourairports import OurAirportsProvider

###############################################################################
def test_opentripmap_requires_key_and_builds_tourism_url() -> None:
    with pytest.raises(ProviderAuthError):
        run_async_in_thread(
            OpenTripMapProvider().fetch(
                ProviderRequest(
                    capability_id="opentripmap_tourism_pois",
                    params={"latitude": 41.9, "longitude": 12.5},
                )
            )
        )

    response = run_async_in_thread(
        OpenTripMapProvider(api_key="tourism-key").fetch(
            ProviderRequest(
                capability_id="opentripmap_tourism_pois",
                params={"latitude": 41.9, "longitude": 12.5, "kinds": "museums"},
            )
        )
    )
    assert response.payload["renderingMode"] == "clustered-points"
    assert "tourism-key" in response.payload["featuresUrl"]
    assert "kinds=museums" in response.payload["featuresUrl"]

###############################################################################
def test_openchargemap_supports_optional_key() -> None:
    response = run_async_in_thread(
        OpenChargeMapProvider(api_key="charge-key").fetch(
            ProviderRequest(
                capability_id="openchargemap_ev_charging",
                params={"latitude": 41.9, "longitude": 12.5},
            )
        )
    )
    keyed = run_async_in_thread(
        OpenChargeMapProvider(api_key="charge-key").fetch(
            ProviderRequest(
                capability_id="openchargemap_ev_charging",
                params={"latitude": 41.9, "longitude": 12.5},
            )
        )
    )

    assert "openchargemap" in response.payload["featuresUrl"]
    assert "charge-key" in keyed.payload["featuresUrl"]

###############################################################################
def test_ourairports_returns_source_ready_descriptor() -> None:
    response = run_async_in_thread(
        OurAirportsProvider().fetch(ProviderRequest(capability_id="ourairports_airports"))
    )

    assert response.payload["status"] == "source-ready"
    assert response.payload["downloadUrl"].endswith("airports.csv")

###############################################################################
def test_opentripmap_live_fetch_normalizes_geojson() -> None:
    async def fetcher(url, headers):
        assert "api.opentripmap.com" in url
        assert headers is None
        return {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"xid": "x1", "name": "Museum", "kinds": "museums"},
                    "geometry": {"type": "Point", "coordinates": [12.5, 41.9]},
                }
            ],
        }

    response = run_async_in_thread(
        OpenTripMapProvider(api_key="tourism-key", fetcher=fetcher).fetch(
            ProviderRequest(
                capability_id="opentripmap_tourism_pois",
                params={"latitude": 41.9, "longitude": 12.5, "live": True},
            )
        )
    )

    assert response.payload["featureCount"] == 1
    assert response.payload["features"][0]["category"] == "tourism"

###############################################################################
def test_openchargemap_live_fetch_handles_empty_payload() -> None:
    async def fetcher(url, headers):
        assert "api.openchargemap.io" in url
        assert headers is None
        return []

    response = run_async_in_thread(
        OpenChargeMapProvider(api_key="charge-key", fetcher=fetcher).fetch(
            ProviderRequest(
                capability_id="openchargemap_ev_charging",
                params={"latitude": 41.9, "longitude": 12.5, "live": True},
            )
        )
    )

    assert response.payload["features"] == []
    assert response.payload["featureCount"] == 0

def test_optional_live_provider_malformed_payload_fails_cleanly() -> None:
    async def fetcher(url, headers):
        return "not-json-shape"

    with pytest.raises(ProviderUnavailableError):
        run_async_in_thread(
            OpenChargeMapProvider(api_key="charge-key", fetcher=fetcher).fetch(
                ProviderRequest(
                    capability_id="openchargemap_ev_charging",
                    params={"latitude": 41.9, "longitude": 12.5, "live": True},
                )
            )
        )

###############################################################################
def test_optional_live_provider_uses_stale_cache_on_failure() -> None:
    calls = 0

    async def fetcher(url, headers):
        nonlocal calls
        calls += 1
        if calls == 1:
            return []
        raise ProviderUnavailableError("timeout")

    clock = {"now": 0.0}
    cache = GeospatialCache(clock=lambda: clock["now"])
    provider = OpenChargeMapProvider(api_key="charge-key", fetcher=fetcher, cache=cache)
    request = ProviderRequest(
        capability_id="openchargemap_ev_charging",
        params={"latitude": 41.9, "longitude": 12.5, "live": True},
    )
    first = run_async_in_thread(provider.fetch(request))
    clock["now"] = 901.0
    second = run_async_in_thread(provider.fetch(request))

    assert first.stale is False
    assert second.stale is True
    assert "stale cached" in second.warnings[0]
