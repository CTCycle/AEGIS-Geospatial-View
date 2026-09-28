from __future__ import annotations

from tests.conftest import run_async_in_thread

import pytest

from server.services.geospatial.providers.base import (
    ProviderAuthError,
    ProviderRequest,
    ProviderUnavailableError,
)
from server.services.geospatial.providers.fema import (
    FEMA_NFHL_EXPORT_URL,
    FEMAProvider,
)
from server.services.geospatial.providers.nasa_firms import NASAFIRMSProvider
from server.services.geospatial.providers.noaa import NOAAProvider
from server.services.geospatial.providers.usgs import USGSProvider

###############################################################################
def test_usgs_provider_builds_earthquake_and_water_urls() -> None:
    earthquake = run_async_in_thread(
        USGSProvider().fetch(ProviderRequest(capability_id="usgs_earthquakes"))
    )
    water = run_async_in_thread(
        USGSProvider().fetch(
            ProviderRequest(
                capability_id="usgs_water_gauges",
                bbox=(-78.0, 38.0, -77.0, 39.0),
            )
        )
    )

    assert earthquake.payload["renderingMode"] == "clustered-points"
    assert "earthquake.usgs.gov" in earthquake.payload["featuresUrl"]
    assert earthquake.payload["legend"]["type"]
    assert (
        "api.waterdata.usgs.gov/ogcapi/v0/collections/latest-continuous/items"
        in water.payload["featuresUrl"]
    )
    assert "bbox=-78.0%2C38.0%2C-77.0%2C39.0" in water.payload["featuresUrl"]
    assert water.payload["freshnessLabel"]

###############################################################################
def test_usgs_provider_normalizes_live_earthquake_geojson() -> None:
    async def fetcher(url: str, headers=None):  # noqa: ANN001
        assert "all_day.geojson" in url
        return {
            "type": "FeatureCollection",
            "features": [
                {
                    "id": "quake-1",
                    "properties": {
                        "place": "10 km S of Test",
                        "mag": 2.5,
                        "time": 1778486400000,
                        "url": "https://earthquake.usgs.gov/quake-1",
                    },
                    "geometry": {"type": "Point", "coordinates": [-122.1, 38.2, 5.0]},
                }
            ],
        }

    response = run_async_in_thread(
        USGSProvider(fetcher=fetcher).fetch(
            ProviderRequest(capability_id="usgs_earthquakes", params={"live": True})
        )
    )

    assert response.payload["totalResults"] == 1
    assert response.payload["features"][0]["category"] == "earthquake"
    assert response.payload["features"][0]["magnitude"] == 2.5

###############################################################################
def test_usgs_bbox_filter_preserves_antimeridian_scope() -> None:
    async def fetcher(url: str, headers=None):  # noqa: ANN001
        _ = url, headers
        return {
            "type": "FeatureCollection",
            "features": [
                {
                    "id": "east-edge",
                    "properties": {"place": "east", "mag": 1.0},
                    "geometry": {"type": "Point", "coordinates": [179.5, 0.0]},
                },
                {
                    "id": "west-edge",
                    "properties": {"place": "west", "mag": 1.0},
                    "geometry": {"type": "Point", "coordinates": [-179.5, 0.0]},
                },
                {
                    "id": "middle",
                    "properties": {"place": "middle", "mag": 1.0},
                    "geometry": {"type": "Point", "coordinates": [0.0, 0.0]},
                },
            ],
        }

    response = run_async_in_thread(
        USGSProvider(fetcher=fetcher).fetch(
            ProviderRequest(
                capability_id="usgs_earthquakes",
                bbox=(170.0, -10.0, -170.0, 10.0),
                params={"live": True},
            )
        )
    )

    assert [item["id"] for item in response.payload["features"]] == [
        "east-edge",
        "west-edge",
    ]

###############################################################################
def test_usgs_provider_normalizes_live_water_gauges() -> None:
    async def fetcher(url: str, headers=None):  # noqa: ANN001
        assert (
            "api.waterdata.usgs.gov/ogcapi/v0/collections/latest-continuous/items"
            in url
        )
        return {
            "type": "FeatureCollection",
            "features": [
                {
                    "id": "USGS-01646500",
                    "geometry": {"type": "Point", "coordinates": [-77.127, 38.949]},
                    "properties": {
                        "monitoring_location_id": "01646500",
                        "monitoring_location_name": "Potomac River",
                        "parameter_code": "00065",
                        "value": 4.1,
                        "time": "2026-05-11T12:00:00Z",
                        "unit_of_measure": "ft",
                    },
                }
            ],
        }

    response = run_async_in_thread(
        USGSProvider(fetcher=fetcher).fetch(
            ProviderRequest(capability_id="usgs_water_gauges", params={"live": True})
        )
    )

    assert response.payload["totalResults"] == 1
    assert response.payload["features"][0]["id"] == "01646500"
    assert response.payload["features"][0]["metadata"]["unit"] == "ft"

###############################################################################
def test_noaa_provider_builds_alert_radar_and_coops_descriptors() -> None:
    alerts = run_async_in_thread(
        NOAAProvider().fetch(ProviderRequest(capability_id="noaa_weather_alerts"))
    )
    radar = run_async_in_thread(
        NOAAProvider().fetch(ProviderRequest(capability_id="noaa_radar"))
    )
    coops = run_async_in_thread(
        NOAAProvider().fetch(ProviderRequest(capability_id="noaa_coops_water_levels"))
    )

    assert alerts.payload["renderingMode"] == "geojson"
    assert alerts.payload["legend"]["label"]
    assert radar.payload["renderingMode"] == "raster-tile"
    assert radar.payload["legend"]["label"]
    assert coops.payload["status"] == "server-side-only"
    assert "featuresUrl" not in coops.payload
    assert coops.payload["freshnessLabel"]

###############################################################################
def test_noaa_provider_normalizes_live_alert_geojson() -> None:
    async def fetcher(url: str, headers=None):  # noqa: ANN001
        assert "api.weather.gov/alerts/active" in url
        assert headers and "User-Agent" in headers
        return {
            "type": "FeatureCollection",
            "features": [
                {
                    "id": "alert-1",
                    "properties": {
                        "event": "Flood Warning",
                        "severity": "Severe",
                        "certainty": "Likely",
                        "urgency": "Expected",
                        "areaDesc": "Test County",
                        "effective": "2026-05-11T12:00:00Z",
                        "expires": "2026-05-11T18:00:00Z",
                        "senderName": "NWS Test",
                    },
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[[-77.0, 38.0], [-76.9, 38.0], [-77.0, 38.0]]],
                    },
                }
            ],
        }

    response = run_async_in_thread(
        NOAAProvider(fetcher=fetcher).fetch(
            ProviderRequest(
                capability_id="noaa_weather_alerts",
                bbox=(-78.0, 38.0, -77.0, 39.0),
                params={"live": True},
            )
        )
    )

    assert response.payload["totalResults"] == 1
    assert response.payload["features"][0]["category"] == "weather_alert"
    assert response.payload["features"][0]["severity"] == "Severe"

###############################################################################
def test_noaa_provider_resolves_missing_alert_geometry_from_affected_zones() -> None:
    calls: list[str] = []
    zone_urls = [
        "https://api.weather.gov/zones/forecast/TXZ213",
        "https://api.weather.gov/zones/forecast/TXZ237",
    ]

    async def fetcher(url: str, headers=None):  # noqa: ANN001
        calls.append(url)
        assert headers and "User-Agent" in headers
        if "api.weather.gov/alerts/active" in url:
            return {
                "type": "FeatureCollection",
                "features": [
                    {
                        "id": "alert-air-quality",
                        "properties": {
                            "event": "Air Quality Alert",
                            "areaDesc": "Houston area",
                            "affectedZones": [
                                *zone_urls,
                                "https://attacker.example/zones/forecast/NOPE",
                            ],
                            "geocode": {"UGC": ["TXZ213", "TXZ237", "BAD"]},
                        },
                        "geometry": None,
                    }
                ],
            }
        assert url in zone_urls
        return {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [-95.6, 29.5],
                        [-95.3, 29.5],
                        [-95.3, 29.9],
                        [-95.6, 29.9],
                        [-95.6, 29.5],
                    ]
                ],
            },
        }

    response = run_async_in_thread(
        NOAAProvider(fetcher=fetcher).fetch(
            ProviderRequest(
                capability_id="noaa_weather_alerts",
                bbox=(-96.0, 29.0, -95.0, 30.0),
                params={"live": True},
            )
        )
    )

    assert calls[0].startswith("https://api.weather.gov/alerts/active")
    assert sorted(calls[1:]) == zone_urls
    feature = response.payload["features"][0]
    assert feature["geometry"]["type"] == "GeometryCollection"
    assert len(feature["geometry"]["geometries"]) == 2
    assert feature["metadata"]["geometrySource"] == "affected_zones"
    assert response.result_status == "ok"
    assert response.partial is False
    assert response.warnings == []


###############################################################################
def test_noaa_provider_keeps_alert_data_when_zone_geometry_is_temporarily_unavailable() -> None:
    async def fetcher(url: str, headers=None):  # noqa: ANN001
        if "api.weather.gov/alerts/active" in url:
            return {
                "type": "FeatureCollection",
                "features": [
                    {
                        "id": "alert-zone-failure",
                        "properties": {
                            "event": "Air Quality Alert",
                            "affectedZones": [
                                "https://api.weather.gov/zones/forecast/TXZ213"
                            ],
                        },
                        "geometry": None,
                    }
                ],
            }
        raise ProviderUnavailableError("zone service unavailable")

    response = run_async_in_thread(
        NOAAProvider(fetcher=fetcher).fetch(
            ProviderRequest(
                capability_id="noaa_weather_alerts",
                params={"live": True},
            )
        )
    )

    assert response.result_status == "partial"
    assert response.partial is True
    assert response.payload["features"][0]["geometry"] is None
    assert response.payload["features"][0]["metadata"]["geometrySource"] == "unresolved"
    assert any("zone" in warning.casefold() for warning in response.warnings)

###############################################################################
def test_fema_provider_builds_nfhl_tile_descriptor() -> None:
    response = run_async_in_thread(
        FEMAProvider().fetch(ProviderRequest(capability_id="fema_nfhl_flood_zones"))
    )

    assert response.result_status == "ok"
    assert response.result_type == "raster"
    assert response.payload["renderingMode"] == "raster-tile"
    assert response.payload["tileUrl"] == FEMA_NFHL_EXPORT_URL
    assert "/arcgis/rest/services/public/NFHL/MapServer/export" in response.payload[
        "tileUrl"
    ]
    assert response.payload["legend"]["type"]

###############################################################################
def test_nasa_firms_requires_key_before_descriptor() -> None:
    with pytest.raises(ProviderAuthError):
        run_async_in_thread(
            NASAFIRMSProvider().fetch(
                ProviderRequest(
                    capability_id="nasa_firms_active_fires",
                    bbox=(-123.0, 38.0, -121.0, 40.0),
                )
            )
        )

    response = run_async_in_thread(
        NASAFIRMSProvider(api_key="test-key").fetch(
            ProviderRequest(
                capability_id="nasa_firms_active_fires",
                bbox=(-123.0, 38.0, -121.0, 40.0),
            )
        )
    )
    assert response.payload["status"] == "server-side-only"
    assert "test-key" not in str(response.payload)
    assert response.payload["freshnessLabel"]

###############################################################################
def test_nasa_firms_normalizes_live_csv() -> None:
    async def fetcher(url: str) -> str:
        assert "test-key" in url
        return (
            "latitude,longitude,bright_ti4,confidence,acq_date,acq_time,satellite,instrument,frp,daynight\n"
            "38.2,-122.1,345.6,h,2026-05-11,0930,N,VIIRS,12.4,D\n"
        )

    response = run_async_in_thread(
        NASAFIRMSProvider(api_key="test-key", fetcher=fetcher).fetch(
            ProviderRequest(
                capability_id="nasa_firms_active_fires",
                bbox=(-123.0, 38.0, -121.0, 40.0),
                params={"live": True},
            )
        )
    )

    assert response.payload["totalResults"] == 1
    assert response.payload["features"][0]["category"] == "active_fire"
    assert response.payload["features"][0]["timestamp"] == "2026-05-11T09:30:00Z"
