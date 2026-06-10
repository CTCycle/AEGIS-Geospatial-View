from __future__ import annotations

import asyncio

import pytest

from server.services.geospatial.provider_registry import ProviderRegistry
from server.services.geospatial.providers.base import ProviderAuthError, ProviderRequest
from server.services.geospatial.providers.fema import FEMAProvider
from server.services.geospatial.providers.nasa_firms import NASAFIRMSProvider
from server.services.geospatial.providers.noaa import NOAAProvider
from server.services.geospatial.providers.usgs import USGSProvider


###############################################################################
def test_usgs_provider_builds_earthquake_and_water_urls() -> None:
    earthquake = asyncio.run(
        USGSProvider().fetch(ProviderRequest(capability_id="usgs_earthquakes"))
    )
    water = asyncio.run(
        USGSProvider().fetch(
            ProviderRequest(
                capability_id="usgs_water_gauges",
                bbox=(-78.0, 38.0, -77.0, 39.0),
            )
        )
    )

    assert earthquake.payload["renderingMode"] == "clustered-points"
    assert "earthquake.usgs.gov" in earthquake.payload["featuresUrl"]
    assert "bBox=-78.0%2C38.0%2C-77.0%2C39.0" in water.payload["featuresUrl"]


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

    response = asyncio.run(
        USGSProvider(fetcher=fetcher).fetch(
            ProviderRequest(capability_id="usgs_earthquakes", params={"live": True})
        )
    )

    assert response.payload["totalResults"] == 1
    assert response.payload["features"][0]["category"] == "earthquake"
    assert response.payload["features"][0]["magnitude"] == 2.5


###############################################################################
def test_usgs_provider_normalizes_live_water_gauges() -> None:
    async def fetcher(url: str, headers=None):  # noqa: ANN001
        assert "waterservices.usgs.gov" in url
        return {
            "value": {
                "timeSeries": [
                    {
                        "sourceInfo": {
                            "siteName": "Potomac River",
                            "siteCode": [{"value": "01646500"}],
                            "geoLocation": {
                                "geogLocation": {
                                    "latitude": 38.949,
                                    "longitude": -77.127,
                                }
                            },
                        },
                        "variable": {
                            "variableName": "Gage height",
                            "unit": {"unitCode": "ft"},
                        },
                        "values": [
                            {
                                "value": [
                                    {"value": "4.1", "dateTime": "2026-05-11T12:00:00Z"}
                                ]
                            }
                        ],
                    }
                ]
            }
        }

    response = asyncio.run(
        USGSProvider(fetcher=fetcher).fetch(
            ProviderRequest(capability_id="usgs_water_gauges", params={"live": True})
        )
    )

    assert response.payload["totalResults"] == 1
    assert response.payload["features"][0]["id"] == "01646500"
    assert response.payload["features"][0]["metadata"]["unit"] == "ft"


###############################################################################
def test_noaa_provider_builds_alert_radar_and_coops_descriptors() -> None:
    alerts = asyncio.run(
        NOAAProvider().fetch(ProviderRequest(capability_id="noaa_weather_alerts"))
    )
    radar = asyncio.run(
        NOAAProvider().fetch(ProviderRequest(capability_id="noaa_radar"))
    )
    coops = asyncio.run(
        NOAAProvider().fetch(ProviderRequest(capability_id="noaa_coops_water_levels"))
    )

    assert alerts.payload["renderingMode"] == "geojson"
    assert radar.payload["renderingMode"] == "raster-tile"
    assert "tidesandcurrents.noaa.gov" in coops.payload["featuresUrl"]


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

    response = asyncio.run(
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
def test_fema_provider_builds_nfhl_tile_descriptor() -> None:
    response = asyncio.run(
        FEMAProvider().fetch(ProviderRequest(capability_id="fema_nfhl_flood_zones"))
    )

    assert response.payload["renderingMode"] == "wms"
    assert "hazards.fema.gov" in response.payload["tileUrl"]


###############################################################################
def test_nasa_firms_requires_key_before_descriptor() -> None:
    with pytest.raises(ProviderAuthError):
        asyncio.run(
            NASAFIRMSProvider().fetch(
                ProviderRequest(
                    capability_id="nasa_firms_active_fires",
                    bbox=(-123.0, 38.0, -121.0, 40.0),
                )
            )
        )

    response = asyncio.run(
        NASAFIRMSProvider(api_key="test-key").fetch(
            ProviderRequest(
                capability_id="nasa_firms_active_fires",
                bbox=(-123.0, 38.0, -121.0, 40.0),
            )
        )
    )
    assert "test-key" in response.payload["featuresUrl"]


###############################################################################
def test_nasa_firms_normalizes_live_csv() -> None:
    async def fetcher(url: str) -> str:
        assert "test-key" in url
        return (
            "latitude,longitude,bright_ti4,confidence,acq_date,acq_time,satellite,instrument,frp,daynight\n"
            "38.2,-122.1,345.6,h,2026-05-11,0930,N,VIIRS,12.4,D\n"
        )

    response = asyncio.run(
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


###############################################################################
def test_provider_registry_binds_hazard_adapters_from_manifests() -> None:
    registry = ProviderRegistry()

    registry.build_from_manifests()

    for provider_id in ("usgs", "noaa", "fema", "nasa_firms"):
        assert provider_id in registry.list_provider_ids()
