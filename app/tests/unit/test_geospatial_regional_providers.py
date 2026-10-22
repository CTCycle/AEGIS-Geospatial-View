from __future__ import annotations
from datetime import UTC, datetime
from tests.conftest import run_async_in_thread
import pytest
import asyncio
from server.services.geospatial.providers.base import ProviderAuthError, ProviderInvalidQueryError, ProviderRequest, ProviderUnavailableError
from server.services.geospatial.providers.fema import FEMA_NFHL_EXPORT_URL, FEMAProvider
from server.services.geospatial.providers.nasa_firms import NASAFIRMSProvider
from server.services.geospatial.providers.noaa import NOAAProvider
from server.services.geospatial.providers.usgs import USGSProvider
from server.services.geospatial.providers import emsc as emsc_module
from server.services.geospatial.providers.emsc import EMSC_FDSN_URL, EMSCProvider
from server.services.geospatial.cache import GeospatialCache
from server.services.geospatial.providers.eea import EEAProvider
from server.services.geospatial.providers.esa import ESAProvider
from server.services.geospatial.providers.eurostat import EurostatProvider
from server.services.geospatial.manifest_loader import GeospatialManifestLoader
from server.services.geospatial.provider_registry import ProviderRegistry
from server.services.geospatial.providers.soilgrids import SoilGridsProvider
from server.services.geospatial.runtime_registry import RuntimeRegistry

# --- test_hazard_provider_adapters.py ---





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

# --- test_regional_provider_adapters.py ---



###############################################################################
def test_eea_provider_returns_wms_descriptor() -> None:
    response = run_async_in_thread(
        EEAProvider().fetch(
            ProviderRequest(
                capability_id="eea_noise_end2022",
                params={
                    "metadata": {
                        "url": "https://example.test/wms",
                        "layers": "0,17,34,51",
                        "wms_version": "1.1.1",
                        "wms_exceptions": "application/vnd.ogc.se_xml",
                        "attribution": "EEA",
                    }
                },
            )
        )
    )

    assert response.payload["renderingMode"] == "wms"
    assert response.payload["serviceUrl"] == "https://example.test/wms"
    assert response.payload["layers"] == ["0,17,34,51"]
    assert response.payload["version"] == "1.1.1"
    assert response.payload["exceptions"] == "application/vnd.ogc.se_xml"
    assert response.payload["freshnessLabel"] == (
        "END-2022 reporting vintage; service updated 2025"
    )
    assert response.result_type == "raster"
    assert response.attribution == ["EEA"]

###############################################################################
def test_eea_provider_live_validation_uses_stale_cache_after_failure() -> None:
    clock = 0.0

    def now() -> float:
        return clock

    async def ok_fetcher(url: str, headers: dict[str, str] | None = None):
        return {"service": "WMS", "layers": ["0"]}

    provider = EEAProvider(
        fetcher=ok_fetcher,
        cache=GeospatialCache(clock=now),
        cache_ttl_seconds=1,
        stale_while_revalidate_seconds=10,
    )
    request = ProviderRequest(
        capability_id="eea_noise_end2022",
        params={"live_validate": True, "metadata": {"url": "https://example.test/wms"}},
    )
    first = run_async_in_thread(provider.fetch(request))

    async def failing_fetcher(url: str, headers: dict[str, str] | None = None):
        raise ProviderUnavailableError("timeout")

    clock = 2.0
    provider.fetcher = failing_fetcher
    stale = run_async_in_thread(provider.fetch(request))

    assert first.payload["liveValidation"]["service"] == "WMS"
    assert stale.stale is True
    assert stale.payload["liveValidation"]["layers"] == ["0"]
    assert stale.warnings

###############################################################################
def test_eea_provider_rejects_malformed_live_validation_without_cache() -> None:
    async def malformed_fetcher(url: str, headers: dict[str, str] | None = None):
        return ["not", "metadata"]

    with pytest.raises(ProviderUnavailableError):
        run_async_in_thread(
            EEAProvider(fetcher=malformed_fetcher).fetch(
                ProviderRequest(
                    capability_id="eea_noise_end2022",
                    params={
                        "live_validate": True,
                        "metadata": {"url": "https://example.test/wms"},
                    },
                )
            )
        )

###############################################################################
def test_esa_provider_returns_wms_descriptor_with_metadata() -> None:
    response = run_async_in_thread(
        ESAProvider().fetch(
            ProviderRequest(
                capability_id="esa_worldcover",
                params={
                    "metadata": {
                        "url": "https://example.test/wms",
                        "layer_id": "esa-worldcover-map-10m-2021-v2_map",
                        "source_protocol": "WMS",
                        "crs": "EPSG:3857",
                        "format": "image/png",
                        "wms_version": "1.3.0",
                        "wms_exceptions": "application/vnd.ogc.se_inimage",
                        "attribution": "ESA",
                    }
                },
            )
        )
    )

    assert response.payload["renderingMode"] == "wms"
    assert response.payload["layerId"] == "esa-worldcover-map-10m-2021-v2_map"
    assert response.payload["layers"] == "esa-worldcover-map-10m-2021-v2_map"
    assert response.payload["serviceUrl"] == "https://example.test/wms"
    assert response.payload["crs"] == "EPSG:3857"
    assert response.payload["format"] == "image/png"
    assert response.payload["version"] == "1.3.0"
    assert response.payload["exceptions"] == "application/vnd.ogc.se_inimage"
    assert response.payload["legend"]["source"] == "ESA WorldCover / Terrascope"
    assert response.payload["freshnessLabel"] == "WorldCover 2021 static source layer"
    assert response.result_type == "raster"
    assert response.attribution == ["ESA"]

###############################################################################
def test_esa_provider_preserves_wmts_descriptor_compatibility() -> None:
    response = run_async_in_thread(
        ESAProvider().fetch(
            ProviderRequest(
                capability_id="esa_worldcover",
                params={
                    "metadata": {
                        "url": "https://example.test/wmts",
                        "source_protocol": "WMTS",
                        "layer_id": "WORLDCOVER_2021_MAP",
                        "tile_matrix_set": "EPSG:3857",
                        "wmts_format": "image/png",
                        "wmts_style": "default",
                    }
                },
            )
        )
    )

    assert response.payload["renderingMode"] == "wmts"
    assert response.payload["serviceUrl"] == "https://example.test/wmts"
    assert response.payload["layerId"] == "WORLDCOVER_2021_MAP"
    assert response.payload["tileMatrixSet"] == "EPSG:3857"
    assert response.payload["format"] == "image/png"
    assert response.payload["style"] == "default"
    assert response.payload["legend"]["source"] == "ESA WorldCover / Terrascope"

###############################################################################
def test_esa_provider_live_validation_handles_timeout_and_stale_cache() -> None:
    clock = 0.0

    def now() -> float:
        return clock

    async def ok_fetcher(url: str, headers: dict[str, str] | None = None):
        return {"service": "WMS", "layers": ["esa-worldcover-map-10m-2021-v2_map"]}

    provider = ESAProvider(
        fetcher=ok_fetcher,
        cache=GeospatialCache(clock=now),
        cache_ttl_seconds=1,
        stale_while_revalidate_seconds=10,
    )
    request = ProviderRequest(
        capability_id="esa_worldcover",
        params={
            "live_validate": True,
            "metadata": {
                "url": "https://example.test/wms",
                "source_protocol": "WMS",
                "layer_id": "esa-worldcover-map-10m-2021-v2_map",
            },
        },
    )
    run_async_in_thread(provider.fetch(request))

    async def timeout_fetcher(url: str, headers: dict[str, str] | None = None):
        raise TimeoutError("timed out")

    clock = 2.0
    provider.fetcher = timeout_fetcher
    stale = run_async_in_thread(provider.fetch(request))

    assert stale.stale is True
    assert stale.payload["liveValidation"]["service"] == "WMS"

###############################################################################
def test_eurostat_provider_keeps_statistics_metadata_only_until_joined() -> None:
    response = run_async_in_thread(
        EurostatProvider().fetch(
            ProviderRequest(
                capability_id="eurostat_regional_demographics",
                params={"metadata": {"url": "https://example.test/jsonstat"}},
            )
        )
    )

    assert response.payload["renderingMode"] == "metadata-only"
    assert response.payload["joinRequired"] is True
    assert response.payload["joinKey"] == "NUTS_ID"

###############################################################################
def test_eurostat_provider_validates_jsonstat_metadata_and_stale_cache() -> None:
    clock = 0.0

    def now() -> float:
        return clock

    async def ok_fetcher(url: str, headers: dict[str, str] | None = None):
        return {
            "label": "Population density",
            "id": ["geo", "time"],
            "size": [1, 1],
            "dimension": {"geo": {}, "time": {}},
            "updated": "2026-01-01",
        }

    provider = EurostatProvider(
        fetcher=ok_fetcher,
        cache=GeospatialCache(clock=now),
        cache_ttl_seconds=1,
        stale_while_revalidate_seconds=10,
    )
    request = ProviderRequest(
        capability_id="eurostat_regional_demographics",
        params={
            "live_validate": True,
            "metadata": {"url": "https://example.test/jsonstat"},
        },
    )
    first = run_async_in_thread(provider.fetch(request))

    async def malformed_fetcher(url: str, headers: dict[str, str] | None = None):
        return {"value": []}

    clock = 2.0
    provider.fetcher = malformed_fetcher
    stale = run_async_in_thread(provider.fetch(request))

    assert first.payload["jsonStatMetadata"]["dimensions"] == ["geo", "time"]
    assert stale.stale is True
    assert stale.payload["jsonStatMetadata"]["label"] == "Population density"

###############################################################################
def test_eurostat_provider_rejects_malformed_jsonstat_without_cache() -> None:
    async def malformed_fetcher(url: str, headers: dict[str, str] | None = None):
        return {"value": []}

    with pytest.raises(ProviderUnavailableError):
        run_async_in_thread(
            EurostatProvider(fetcher=malformed_fetcher).fetch(
                ProviderRequest(
                    capability_id="eurostat_regional_demographics",
                    params={
                        "live_validate": True,
                        "metadata": {"url": "https://example.test/jsonstat"},
                    },
                )
            )
        )

###############################################################################
def test_eurostat_provider_builds_fixture_backed_choropleth_payload() -> None:
    response = run_async_in_thread(
        EurostatProvider().fetch(
            ProviderRequest(
                capability_id="eurostat_regional_demographics",
                params={
                    "metric": "population_density",
                    "vintage": "2024",
                    "margin_of_error": 1.5,
                    "joined_features": [
                        {
                            "type": "Feature",
                            "properties": {"NUTS_ID": "IT", "value": 201.2},
                            "geometry": {
                                "type": "Polygon",
                                "coordinates": [
                                    [
                                        [12.0, 41.0],
                                        [13.0, 41.0],
                                        [13.0, 42.0],
                                        [12.0, 41.0],
                                    ]
                                ],
                            },
                        },
                        {
                            "type": "Feature",
                            "properties": {"NUTS_ID": "FR", "value": 123.4},
                            "geometry": {
                                "type": "Polygon",
                                "coordinates": [
                                    [[2.0, 48.0], [3.0, 48.0], [3.0, 49.0], [2.0, 48.0]]
                                ],
                            },
                        },
                    ],
                },
            )
        )
    )

    assert response.payload["renderingMode"] == "choropleth"
    assert response.payload["metric"] == "population_density"
    assert response.payload["vintage"] == "2024"
    assert response.payload["marginOfError"] == 1.5
    assert response.payload["source"] == "Eurostat"
    assert len(response.payload["legendBins"]) == 4
    feature = response.payload["featureCollection"]["features"][0]
    assert feature["properties"]["metric"] == "population_density"
    assert feature["properties"]["marginOfError"] == 1.5

###############################################################################
def test_eurostat_provider_describes_nuts_ingestion_payload() -> None:
    response = run_async_in_thread(
        EurostatProvider().fetch(
            ProviderRequest(
                capability_id="eurostat_nuts_regions",
                params={"source_url": "https://example.test/nuts.geojson"},
            )
        )
    )

    assert response.payload["renderingMode"] == "vector-tile"
    assert response.payload["status"] == "dataset-ingestion"
    assert response.payload["joinKey"] == "NUTS_ID"

# --- test_soilgrids_provider.py ---




###############################################################################
def test_soilgrids_provider_builds_default_wcs_descriptors() -> None:
    response = asyncio.run(
        SoilGridsProvider().fetch(
            ProviderRequest(capability_id="soilgrids_soil_properties")
        )
    )

    assert response.provider_id == "soilgrids"
    assert response.payload["property"] == "phh2o"
    assert response.payload["depth"] == "0-5cm"
    assert response.payload["quantile"] == "mean"
    assert response.payload["coverageId"] == "phh2o_0-5cm_mean"
    assert response.payload["renderingMode"] == "metadata-only"
    assert "SERVICE=WCS" in response.payload["wcsCapabilitiesUrl"]
    assert "REQUEST=DescribeCoverage" in response.payload["describeCoverageUrl"]
    assert response.payload["coverageDownloadUrl"] is None
    assert response.payload["spatialResolution"] == "250 m"

###############################################################################
def test_soilgrids_provider_builds_bounded_geotiff_coverage_url() -> None:
    response = asyncio.run(
        SoilGridsProvider().fetch(
            ProviderRequest(
                capability_id="soilgrids_soil_properties",
                bbox=(8.50, 47.35, 8.60, 47.45),
                params={
                    "property": "clay",
                    "depth": "30-60cm",
                    "quantile": "Q0.95",
                },
            )
        )
    )

    assert response.payload["coverageId"] == "clay_30-60cm_Q0.95"
    assert response.payload["propertyLabel"] == "Clay"
    assert response.payload["mappedUnit"] == "g/kg"
    assert response.payload["conversionFactor"] == 10
    coverage_url = response.payload["coverageDownloadUrl"]
    assert coverage_url is not None
    assert "REQUEST=GetCoverage" in coverage_url
    assert "COVERAGEID=clay_30-60cm_Q0.95" in coverage_url
    assert "FORMAT=GEOTIFF_INT16" in coverage_url
    assert "SUBSETTINGCRS=" in coverage_url
    assert coverage_url.count("SUBSET=") == 2

###############################################################################
def test_soilgrids_provider_handles_organic_carbon_stock_depth_constraints() -> None:
    response = asyncio.run(
        SoilGridsProvider().fetch(
            ProviderRequest(
                capability_id="soilgrids_soil_properties",
                params={"property": "ocs", "depth": "0-30cm", "quantile": "mean"},
            )
        )
    )

    assert response.payload["coverageId"] == "ocs_0-30cm_mean"
    assert response.payload["availableDepths"] == ["0-30cm"]
    assert response.payload["availableQuantiles"] == ["mean"]

###############################################################################
def test_soilgrids_provider_rejects_unknown_property() -> None:
    with pytest.raises(ProviderUnavailableError, match="Unsupported SoilGrids property"):
        asyncio.run(
            SoilGridsProvider().fetch(
                ProviderRequest(
                    capability_id="soilgrids_soil_properties",
                    params={"property": "not-a-soil-property"},
                )
            )
        )

###############################################################################
def test_soilgrids_manifest_and_runtime_profile_are_loaded() -> None:
    loaded = GeospatialManifestLoader().load_all()

    capability = next(
        item
        for item in loaded["overlays"]
        if item["id"] == "soilgrids_soil_properties"
    )
    profile = next(
        item
        for item in loaded["runtime_profiles"]
        if item["capability_id"] == "soilgrids_soil_properties"
    )

    assert capability["provider"] == "soilgrids"
    assert capability["capabilityKind"] == "analysis-tool"
    assert capability["renderingMode"] == "metadata-only"
    assert profile["enabled_by_default"] is True
    assert profile["supports_map"] is False
    assert profile["supports_direct_text"] is True
    assert profile["auth_required"] is False

###############################################################################
def test_soilgrids_is_available_to_runtime_and_provider_registries() -> None:
    runtime_registry = RuntimeRegistry()
    provider_registry = ProviderRegistry()

    assert runtime_registry.is_enabled("soilgrids_soil_properties") is True
    assert runtime_registry.supports_mode("soilgrids_soil_properties", "map") is False
    assert runtime_registry.supports_mode("soilgrids_soil_properties", "text") is True
    assert runtime_registry.credentials_present("soilgrids_soil_properties") is True
    assert "soilgrids" in provider_registry.list_provider_ids()
    assert isinstance(provider_registry.get("soilgrids"), SoilGridsProvider)