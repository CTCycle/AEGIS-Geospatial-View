from __future__ import annotations

from datetime import UTC, datetime

from tests.conftest import run_async_in_thread

import pytest

from server.services.geospatial.providers.base import (
    ProviderAuthError,
    ProviderInvalidQueryError,
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
from server.services.geospatial.providers import emsc as emsc_module
from server.services.geospatial.providers.emsc import EMSC_FDSN_URL, EMSCProvider

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
def test_usgs_dated_range_queries_catalog_with_bbox_and_reports_scope() -> None:
    urls: list[str] = []

    async def fetcher(url: str, headers=None):  # noqa: ANN001
        _ = headers
        urls.append(url)
        return {
            "type": "FeatureCollection",
            "features": [
                {
                    "id": "march-1",
                    "properties": {"place": "Japan", "mag": 5.1, "time": 1710000000000},
                    "geometry": {"type": "Point", "coordinates": [140.0, 36.0, 10.0]},
                }
            ],
        }

    response = run_async_in_thread(
        USGSProvider(fetcher=fetcher).fetch(
            ProviderRequest(
                capability_id="usgs_earthquakes",
                bbox=(129.0, 31.0, 146.0, 46.0),
                time=datetime(2024, 3, 1, tzinfo=UTC),
                params={"live": True, "end_time_iso": "2024-03-31T00:00:00Z"},
            )
        )
    )

    assert "fdsnws/event/1/query" in urls[0]
    assert "starttime=2024-03-01T00%3A00%3A00" in urls[0]
    assert "endtime=2024-03-31T00%3A00%3A00" in urls[0]
    assert "minlongitude=129.0" in urls[0]
    assert response.payload["timeMode"] == "historical"
    assert response.payload["totalResults"] == 1
    assert response.coverage["temporal_scope_satisfied"] is True
    assert response.coverage["bbox"] == [129.0, 31.0, 146.0, 46.0]
    assert response.coverage["truncated"] is False
    assert "M4.5" in response.coverage["completeness_note"]
    assert response.observation_time == "2024-03-09T16:00:00+00:00"

###############################################################################
def test_usgs_dated_range_empty_is_valid_empty_and_bad_ranges_are_rejected() -> None:
    async def fetcher(url: str, headers=None):  # noqa: ANN001
        _ = url, headers
        return {"type": "FeatureCollection", "features": []}

    start = datetime(2024, 3, 1, tzinfo=UTC)
    empty = run_async_in_thread(
        USGSProvider(fetcher=fetcher).fetch(
            ProviderRequest(
                capability_id="usgs_earthquakes",
                time=start,
                params={"live": True, "end_time_iso": "2024-03-05T00:00:00Z"},
            )
        )
    )
    assert empty.result_status == "valid_empty"

    for end in ("2024-02-01T00:00:00Z", "2026-03-01T00:00:00Z"):
        with pytest.raises(ProviderInvalidQueryError):
            run_async_in_thread(
                USGSProvider(fetcher=fetcher).fetch(
                    ProviderRequest(
                        capability_id="usgs_earthquakes",
                        time=start,
                        params={"live": True, "end_time_iso": end},
                    )
                )
            )

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
    assert "layers=show:28" in response.payload["tileUrl"]
    assert response.payload["layer"] == "28"
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


###############################################################################
@pytest.mark.asyncio
async def test_usgs_magnitude_filter_feed_and_dated_query():
    urls = []
    async def fetcher(url, headers=None):
        urls.append(url)
        return {"type": "FeatureCollection", "features": [
            {"id": str(mag), "properties": {"mag": mag}, "geometry": {"type": "Point", "coordinates": [8, 45]}}
            for mag in [1, 3, 5]]}
    provider = USGSProvider(fetcher=fetcher)
    feed = await provider.fetch(ProviderRequest(capability_id="usgs_earthquakes", params={"live": True, "filters": {"min_magnitude": 2.5}}))
    assert [item["magnitude"] for item in feed.payload["features"]] == [3, 5]
    assert feed.coverage["min_magnitude"] == 2.5
    await provider.fetch(ProviderRequest(capability_id="usgs_earthquakes", time=datetime(2026, 10, 19, tzinfo=UTC),
        params={"live": True, "end_time_iso": "2026-10-20T00:00:00Z", "filters": {"min_magnitude": 2.5}}))
    assert "minmagnitude=2.5" in urls[-1]


###############################################################################
@pytest.mark.asyncio
async def test_emsc_queries_seismicportal_and_normalizes_events():
    urls = []
    async def fetcher(url, headers=None):
        urls.append(url)
        return {"type": "FeatureCollection", "features": [{"id": "20261020_0000162", "properties": {
            "unid": "20261020_0000162", "time": "2026-10-20T11:54:53.055513Z", "flynn_region": "FRANCE",
            "lat": 45.5955, "lon": 3.9241, "depth": 0.0, "mag": 2.1, "magtype": "ml", "auth": "ReNaSS"}}]}
    response = await EMSCProvider(fetcher=fetcher).fetch(ProviderRequest(
        capability_id="emsc_earthquakes", bbox=(-25.0, 34.0, 45.0, 72.0),
        params={"live": True, "filters": {"min_magnitude": 2}}))
    assert urls[0].startswith(EMSC_FDSN_URL) and "format=json" in urls[0]
    assert "minmagnitude=2.0" in urls[0] and "minlatitude=34.0" in urls[0] and "starttime=" in urls[0]
    [event] = response.payload["features"]
    assert event["name"] == "France" and event["magnitude"] == 2.1 and event["time"] == 1792497293055
    assert response.attribution == ["EMSC-CSEM SeismicPortal"]
    assert "M2.5-3" in response.coverage["completeness_note"]


###############################################################################
@pytest.mark.asyncio
async def test_emsc_empty_204_body_is_valid_empty(monkeypatch):
    async def empty_body(url, headers=None):
        return b""
    monkeypatch.setattr(emsc_module, "fetch_bytes_url", empty_body)
    response = await EMSCProvider().fetch(ProviderRequest(
        capability_id="emsc_earthquakes", bbox=(-25.0, 34.0, 45.0, 72.0), params={"live": True}))
    assert response.result_status == "valid_empty"


###############################################################################
@pytest.mark.asyncio
async def test_macro_region_keeps_member_and_nearby_offshore_events_only():
    events = {"anatolia": (39.5, 28.5), "aegean_off_greece": (38.6, 24.3), "athens": (37.98, 23.73)}
    async def fetcher(url, headers=None):
        return {"type": "FeatureCollection", "features": [{"properties": {
            "unid": name, "time": "2026-10-20T11:54:53Z", "lat": lat, "lon": lon, "mag": 3.0}}
            for name, (lat, lon) in events.items()]}
    response = await EMSCProvider(fetcher=fetcher).fetch(ProviderRequest(
        capability_id="emsc_earthquakes", bbox=(-25.0, 34.0, 45.0, 72.0),
        params={"live": True, "macro_region": "Europe"}))
    assert {event["id"] for event in response.payload["features"]} == {"aegean_off_greece", "athens"}
    assert response.coverage["excluded_outside_region_events"] == 1
