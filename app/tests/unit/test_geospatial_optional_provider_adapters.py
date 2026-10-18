from __future__ import annotations

from tests.conftest import run_async_in_thread

import pytest

from server.services.agent.capability_execution import _response_summary
from server.services.geospatial.cache import GeospatialCache
from server.services.geospatial.providers.base import (
    ProviderAuthError,
    ProviderRequest,
    ProviderUnavailableError,
)
from server.services.geospatial.providers.openchargemap import OpenChargeMapProvider
from server.services.geospatial.providers.opentripmap import OpenTripMapProvider
from server.services.geospatial.providers.ourairports import OurAirportsProvider
from server.services.geospatial.providers.tomtom import (
    TomTomProvider,
    build_tomtom_tile_url,
)

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
    assert response.payload["status"] == "server-side-only"
    assert "tourism-key" not in str(response.payload)

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

    assert response.payload["status"] == "server-side-only"
    assert keyed.payload["status"] == "server-side-only"
    assert "charge-key" not in str(response.payload)
    assert "charge-key" not in str(keyed.payload)

###############################################################################
def test_ourairports_returns_source_ready_descriptor() -> None:
    response = run_async_in_thread(
        OurAirportsProvider().fetch(
            ProviderRequest(capability_id="ourairports_airports")
        )
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

###############################################################################
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

###############################################################################
def test_tomtom_incident_point_lies_inside_the_requested_bbox() -> None:
    bbox = (12.0, 41.0, 13.0, 42.0)

    async def fetcher(url, headers):
        return {
            "incidents": [
                {
                    # Starts north of the bbox and runs into it.
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[12.6, 42.2], [12.6, 41.9], [12.6, 41.8]],
                    },
                    "properties": {"id": "entering"},
                },
                {
                    # Crosses the bbox with no vertex inside it.
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[11.5, 41.5], [13.5, 41.5]],
                    },
                    "properties": {"id": "crossing"},
                },
            ]
        }

    response = run_async_in_thread(
        TomTomProvider(api_key="traffic-key", fetcher=fetcher).fetch(
            ProviderRequest(capability_id="tomtom_traffic_incidents", bbox=bbox)
        )
    )

    features = response.payload["features"]
    assert [feature["id"] for feature in features] == ["entering", "crossing"]
    assert (features[0]["longitude"], features[0]["latitude"]) == (12.6, 41.9)
    assert all(
        bbox[0] <= feature["longitude"] <= bbox[2]
        and bbox[1] <= feature["latitude"] <= bbox[3]
        for feature in features
    )

###############################################################################
def test_tomtom_flow_descriptor_is_renderable_raster_evidence() -> None:
    response = run_async_in_thread(
        TomTomProvider(api_key="traffic-key").fetch(
            ProviderRequest(
                capability_id="tomtom_traffic_flow",
                bbox=(12.0, 41.0, 13.0, 42.0),
            )
        )
    )

    assert response.result_type == "raster"
    assert response.payload["tileUrl"].startswith("/api/geospatial/proxy/tomtom/")
    assert "traffic-key" not in str(response.payload)
    assert _response_summary(response)["map_eligibility"] == "renderable"
    # The proxy serves TomTom's documented single-style flow tile path.
    assert build_tomtom_tile_url("traffic-flow", 12, 2190, 1520, "k") == (
        "https://api.tomtom.com/traffic/map/4/tile/flow/absolute/12/2190/1520.png?key=k"
    )
