from __future__ import annotations

import asyncio

import pytest

from server.services.geospatial.provider_registry import ProviderRegistry
from server.services.geospatial.cache import GeospatialCache
from server.services.geospatial.overpass import OverpassRateLimitError, OverpassRequestError
from server.services.geospatial.providers.base import (
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderRequest,
    ProviderUnavailableError,
)
from server.services.geospatial.providers.arcgis_rest import ArcGISRestProvider
from server.services.geospatial.providers.census import CensusProvider
from server.services.geospatial.providers.geoapify import GeoapifyProvider
from server.services.geospatial.providers.nasa_gibs import NASAGIBSProvider
from server.services.geospatial.providers.openaq import OpenAQProvider
from server.services.geospatial.providers.openmeteo import OpenMeteoProvider
from server.services.geospatial.providers.overpass import OverpassProvider
from server.services.geospatial.providers.pvgis import PVGISProvider
from server.services.geospatial.providers.tomtom import TomTomProvider
from server.services.geospatial.providers.windy_webcams import WindyWebcamsProvider


###############################################################################
class _OpenMeteoService:

    # -------------------------------------------------------------------------
    async def get_weather_forecast(self, *, latitude: float, longitude: float):
        return {
            "kind": "weather_forecast",
            "latitude": latitude,
            "longitude": longitude,
            "timezone": "Europe/Rome",
            "current": {
                "temperature_2m": 18,
                "wind_speed_10m": 7,
                "wind_direction_10m": 270,
                "surface_pressure": 1008,
                "relative_humidity_2m": 55,
            },
            "hourly_preview": [
                {
                    "time": "2026-05-11T00:00",
                    "temperature_2m": 18,
                    "wind_speed_10m": 7,
                    "wind_direction_10m": 270,
                }
            ],
            "resolved_at": "2026-05-11T00:00:00+00:00",
            "attribution": "Data from Open-Meteo",
        }

    # -------------------------------------------------------------------------
    async def get_air_quality_forecast(self, *, latitude: float, longitude: float):
        return {
            "kind": "air_quality_forecast",
            "latitude": latitude,
            "longitude": longitude,
            "timezone": "Europe/Rome",
            "hourly_preview": [
                {
                    "time": "2026-05-11T00:00",
                    "pm2_5": 8,
                    "pm10": 12,
                    "nitrogen_dioxide": 20,
                    "ozone": 60,
                }
            ],
            "resolved_at": "2026-05-11T00:00:00+00:00",
            "attribution": "Data from Open-Meteo",
        }


###############################################################################
class _OverpassService:
    default_radius_m = 1000.0
    calls: list[dict[str, object]]

    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        self.calls = []

    # -------------------------------------------------------------------------
    async def get_nearby_poi(self, **kwargs):  # noqa: ANN003
        self.calls.append(dict(kwargs))
        return {
            "items": [
                {
                    "id": "1",
                    "name": "Clinic",
                    "amenity": "clinic",
                    "latitude": kwargs["latitude"],
                    "longitude": kwargs["longitude"],
                }
            ],
            "resolved_at": "2026-05-11T00:00:00+00:00",
            "attribution": "OSM",
        }


###############################################################################
class _OpenAQService:
    default_radius_m = 25000.0

    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        self.calls: list[dict[str, float]] = []

    # -------------------------------------------------------------------------
    async def get_nearby_measurements(self, *, lat: float, lon: float, radius_m: float):
        self.calls.append({"lat": lat, "lon": lon, "radius_m": radius_m})
        return {
            "locations": [
                {
                    "id": 10,
                    "name": "Station",
                    "latitude": lat,
                    "longitude": lon,
                    "measurements": {
                        "pm25": {"value": 8.0, "unit": "ug/m3"},
                        "no2": {"value": 18.0, "unit": "ug/m3"},
                    },
                    "distance_m": 120,
                }
            ],
            "summary": {"pm25": {"mean": 8.0}, "no2": {"mean": 18.0}},
            "center": {"latitude": lat, "longitude": lon},
            "attribution": "OpenAQ",
        }


###############################################################################
class _PVGISService:

    # -------------------------------------------------------------------------
    async def get_point_estimate(self, latitude: float, longitude: float):
        return {
            "latitude": latitude,
            "longitude": longitude,
            "yearly_kwh_per_kwp_estimate": 1234.5,
            "raw": {"monthly": []},
            "attribution": "PVGIS",
        }


###############################################################################
def test_openmeteo_provider_selects_weather_or_air_quality() -> None:
    provider = OpenMeteoProvider(service=_OpenMeteoService())  # type: ignore[arg-type]

    weather = asyncio.run(
        provider.fetch(
            ProviderRequest(
                capability_id="openmeteo_weather_forecast",
                params={"latitude": 41.9, "longitude": 12.5},
            )
        )
    )
    air = asyncio.run(
        provider.fetch(
            ProviderRequest(
                capability_id="openmeteo_air_quality_forecast",
                params={"latitude": 41.9, "longitude": 12.5},
            )
        )
    )

    assert weather.payload["kind"] == "weather_forecast"
    assert weather.payload["renderingMode"] == "metadata-only"
    assert air.payload["kind"] == "air_quality_forecast"
    assert air.payload["renderingMode"] == "clustered-points"
    assert air.payload["features"][0]["metadata"]["pollutantSymbols"]["pm25"] == 8


###############################################################################
def test_openmeteo_provider_returns_wind_arrow_features() -> None:
    provider = OpenMeteoProvider(service=_OpenMeteoService())  # type: ignore[arg-type]

    response = asyncio.run(
        provider.fetch(
            ProviderRequest(
                capability_id="openmeteo_pressure_humidity_wind",
                params={"latitude": 41.9, "longitude": 12.5},
            )
        )
    )

    assert response.payload["renderingMode"] == "clustered-points"
    feature = response.payload["features"][0]
    assert feature["category"] == "wind"
    assert feature["metadata"]["windArrow"] == {"speed": 7, "direction": 270}
    assert feature["metadata"]["pressure"] == 1008


###############################################################################
def test_overpass_provider_normalizes_poi_features_from_bbox() -> None:
    service = _OverpassService()
    provider = OverpassProvider(service=service)  # type: ignore[arg-type]

    response = asyncio.run(
        provider.fetch(
            ProviderRequest(
                capability_id="overpass_poi_amenities",
                bbox=(12.0, 41.0, 13.0, 42.0),
            )
        )
    )

    assert response.payload["renderingMode"] == "clustered-points"
    assert response.payload["features"][0]["category"] == "clinic"
    assert service.calls[0]["amenity_tags"] is None


###############################################################################
def test_overpass_provider_maps_supported_amenity_groups() -> None:
    service = _OverpassService()
    provider = OverpassProvider(service=service)  # type: ignore[arg-type]

    asyncio.run(
        provider.fetch(
            ProviderRequest(
                capability_id="overpass_poi_amenities",
                bbox=(12.0, 41.0, 13.0, 42.0),
                params={"category": "healthcare"},
            )
        )
    )

    assert service.calls[0]["amenity_tags"] == [
        "hospital",
        "clinic",
        "pharmacy",
        "doctors",
    ]


###############################################################################
def test_overpass_provider_propagates_rate_limits_and_timeouts() -> None:

    ###############################################################################
    class _RateLimitedService(_OverpassService):

        # -------------------------------------------------------------------------
        async def get_nearby_poi(self, **kwargs):  # noqa: ANN003
            raise OverpassRateLimitError("limited")

    ###############################################################################
    class _TimeoutService(_OverpassService):

        # -------------------------------------------------------------------------
        async def get_nearby_poi(self, **kwargs):  # noqa: ANN003
            raise OverpassRequestError("timed out")

    with pytest.raises(ProviderRateLimitError):
        asyncio.run(
            OverpassProvider(service=_RateLimitedService()).fetch(  # type: ignore[arg-type]
                ProviderRequest(
                    capability_id="overpass_poi_amenities",
                    bbox=(12.0, 41.0, 13.0, 42.0),
                )
            )
        )
    with pytest.raises(ProviderUnavailableError):
        asyncio.run(
            OverpassProvider(service=_TimeoutService()).fetch(  # type: ignore[arg-type]
                ProviderRequest(
                    capability_id="overpass_poi_amenities",
                    bbox=(12.0, 41.0, 13.0, 42.0),
                )
            )
        )


###############################################################################
def test_overpass_provider_returns_empty_result() -> None:

    ###############################################################################
    class _EmptyService(_OverpassService):

        # -------------------------------------------------------------------------
        async def get_nearby_poi(self, **kwargs):  # noqa: ANN003
            return {"items": [], "attribution": "OSM"}

    response = asyncio.run(
        OverpassProvider(service=_EmptyService()).fetch(  # type: ignore[arg-type]
            ProviderRequest(
                capability_id="overpass_poi_amenities",
                bbox=(12.0, 41.0, 13.0, 42.0),
            )
        )
    )

    assert response.payload["features"] == []
    assert response.payload["totalResults"] == 0


###############################################################################
def test_openaq_provider_returns_station_features() -> None:
    provider = OpenAQProvider(api_key="openaq-test", service=_OpenAQService())  # type: ignore[arg-type]

    response = asyncio.run(
        provider.fetch(
            ProviderRequest(
                capability_id="openaq_air_quality",
                params={"latitude": 41.9, "longitude": 12.5},
            )
        )
    )

    assert response.payload["features"][0]["measurements"]["pm25"]["value"] == 8.0
    assert response.payload["summary"]["pm25"]["mean"] == 8.0


###############################################################################
def test_openaq_provider_requires_key() -> None:
    with pytest.raises(ProviderAuthError):
        asyncio.run(
            OpenAQProvider(service=_OpenAQService()).fetch(  # type: ignore[arg-type]
                ProviderRequest(capability_id="openaq_air_quality")
            )
        )


###############################################################################
def test_openaq_provider_filters_pollutants() -> None:
    response = asyncio.run(
        OpenAQProvider(api_key="openaq-test", service=_OpenAQService()).fetch(  # type: ignore[arg-type]
            ProviderRequest(
                capability_id="openaq_air_quality",
                params={"latitude": 41.9, "longitude": 12.5, "pollutants": "pm25"},
            )
        )
    )

    assert response.payload["pollutants"] == ["pm25"]
    assert set(response.payload["summary"]) == {"pm25"}
    assert set(response.payload["features"][0]["measurements"]) == {"pm25"}


###############################################################################
def test_openaq_provider_returns_empty_bbox_result() -> None:

    ###############################################################################
    class _EmptyOpenAQService(_OpenAQService):

        # -------------------------------------------------------------------------
        async def get_nearby_measurements(
            self, *, lat: float, lon: float, radius_m: float
        ):
            self.calls.append({"lat": lat, "lon": lon, "radius_m": radius_m})
            return {"locations": [], "summary": {}, "attribution": "OpenAQ"}

    response = asyncio.run(
        OpenAQProvider(api_key="openaq-test", service=_EmptyOpenAQService()).fetch(  # type: ignore[arg-type]
            ProviderRequest(
                capability_id="openaq_air_quality",
                bbox=(12.0, 41.0, 13.0, 42.0),
            )
        )
    )

    assert response.payload["features"] == []
    assert response.payload["summary"] == {}


###############################################################################
def test_openaq_provider_uses_cache_and_stale_fallback() -> None:

    ###############################################################################
    class _FailingOpenAQService(_OpenAQService):

        # -------------------------------------------------------------------------
        async def get_nearby_measurements(
            self, *, lat: float, lon: float, radius_m: float
        ):
            self.calls.append({"lat": lat, "lon": lon, "radius_m": radius_m})
            raise ValueError("malformed")

    clock = 0.0

    def now() -> float:
        return clock

    from server.services.geospatial.cache import GeospatialCache

    service = _OpenAQService()
    provider = OpenAQProvider(
        api_key="openaq-test",
        service=service,  # type: ignore[arg-type]
        cache=GeospatialCache(clock=now),
        cache_ttl_seconds=1,
        stale_while_revalidate_seconds=10,
    )
    request = ProviderRequest(
        capability_id="openaq_air_quality",
        params={"latitude": 41.9, "longitude": 12.5},
    )

    first = asyncio.run(provider.fetch(request))
    second = asyncio.run(provider.fetch(request))
    clock = 2.0
    provider.service = _FailingOpenAQService()  # type: ignore[assignment]
    stale = asyncio.run(provider.fetch(request))

    assert first.payload == second.payload
    assert len(service.calls) == 1
    assert stale.stale is True
    assert stale.payload["features"][0]["name"] == "Station"
    assert stale.warnings


###############################################################################
def test_pvgis_provider_returns_metadata_only_analysis() -> None:
    provider = PVGISProvider(service=_PVGISService())  # type: ignore[arg-type]

    response = asyncio.run(
        provider.fetch(
            ProviderRequest(
                capability_id="pvgis_solar",
                params={"latitude": 41.9, "longitude": 12.5},
            )
        )
    )

    assert response.payload["renderingMode"] == "metadata-only"
    assert response.payload["yearlyKwhPerKwpEstimate"] == 1234.5


###############################################################################
def test_tomtom_and_geoapify_require_keys_before_emitting_urls() -> None:
    with pytest.raises(ProviderAuthError):
        asyncio.run(
            TomTomProvider().fetch(
                ProviderRequest(capability_id="tomtom_traffic_flow")
            )
        )
    with pytest.raises(ProviderAuthError):
        asyncio.run(
            GeoapifyProvider().fetch(ProviderRequest(capability_id="geoapify_osm"))
        )


###############################################################################
def test_tomtom_provider_normalizes_live_incidents() -> None:
    calls: list[str] = []

    async def fetcher(url: str, headers: dict[str, str] | None = None):
        calls.append(url)
        return {
            "incidents": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[12.5, 41.9], [12.6, 42.0]],
                    },
                    "properties": {
                        "id": "incident-1",
                        "iconCategory": 6,
                        "magnitudeOfDelay": 2,
                        "events": [{"description": "Lane closed"}],
                        "roadNumbers": ["A1"],
                        "delay": 120,
                    },
                }
            ]
        }

    response = asyncio.run(
        TomTomProvider(api_key="tomtom-test", fetcher=fetcher).fetch(
            ProviderRequest(
                capability_id="tomtom_traffic_incidents",
                bbox=(12.0, 41.0, 13.0, 42.0),
            )
        )
    )

    assert "key=tomtom-test" in calls[0]
    assert "bbox=12.0%2C41.0%2C13.0%2C42.0" in calls[0]
    assert response.payload["renderingMode"] == "clustered-points"
    assert response.payload["features"][0]["name"] == "Lane closed"
    assert response.payload["features"][0]["metadata"]["roadNumbers"] == ["A1"]


###############################################################################
def test_tomtom_provider_emits_proxy_tile_payload_without_secret() -> None:
    response = asyncio.run(
        TomTomProvider(api_key="tomtom-test").fetch(
            ProviderRequest(capability_id="tomtom_traffic_flow")
        )
    )

    assert response.payload["tileUrl"] == (
        "/api/geospatial/proxy/tomtom/traffic-flow/{z}/{x}/{y}.png"
    )
    assert response.payload["credentialPolicy"] == "server-side-only"
    assert "tomtom-test" not in str(response.payload)


###############################################################################
def test_provider_registry_binds_phase4_adapters_from_manifests() -> None:
    registry = ProviderRegistry()

    registry.build_from_manifests()

    for provider_id in (
        "arcgis",
        "census",
        "gibs",
        "openmeteo",
        "overpass",
        "openaq",
        "pvgis",
        "tomtom",
        "geoapify",
    ):
        assert provider_id in registry.list_provider_ids()


###############################################################################
def test_provider_registry_passes_environment_keys_to_gated_adapters(monkeypatch) -> None:
    monkeypatch.setenv("TOMTOM_API_KEY", "tomtom-test")
    monkeypatch.setenv("GEOAPIFY_API_KEY", "geoapify-test")
    registry = ProviderRegistry()
    registry.build_from_manifests()

    tomtom = asyncio.run(
        registry.fetch("tomtom", ProviderRequest(capability_id="tomtom_traffic_flow"))
    )
    geoapify = asyncio.run(
        registry.fetch("geoapify", ProviderRequest(capability_id="geoapify_osm"))
    )

    assert tomtom.payload["tileUrl"] == (
        "/api/geospatial/proxy/tomtom/traffic-flow/{z}/{x}/{y}.png"
    )
    assert "tomtom-test" not in str(tomtom.payload)
    assert "geoapify-test" in str(geoapify.payload["tileUrl"])


###############################################################################
def test_geoapify_provider_normalizes_live_places() -> None:
    calls: list[str] = []

    async def fetcher(url: str, headers: dict[str, str] | None = None):
        calls.append(url)
        return {
            "features": [
                {
                    "properties": {
                        "place_id": "poi-1",
                        "name": "Clinic",
                        "categories": ["healthcare.clinic"],
                        "formatted": "1 Test Street",
                    },
                    "geometry": {"type": "Point", "coordinates": [12.5, 41.9]},
                }
            ]
        }

    response = asyncio.run(
        GeoapifyProvider(api_key="geoapify-test", fetcher=fetcher).fetch(
            ProviderRequest(
                capability_id="geoapify_amenities",
                bbox=(12.0, 41.0, 13.0, 42.0),
                params={"live": True, "categories": "healthcare"},
            )
        )
    )

    assert "apiKey=geoapify-test" in calls[0]
    assert "filter=rect%3A12.0%2C42.0%2C13.0%2C41.0" in calls[0]
    assert response.payload["totalResults"] == 1
    assert response.payload["features"][0]["source"] == "geoapify"


###############################################################################
def test_geoapify_provider_caches_live_places_by_bbox_and_category() -> None:
    calls: list[str] = []

    async def fetcher(url: str, headers: dict[str, str] | None = None):
        calls.append(url)
        return {
            "features": [
                {
                    "properties": {
                        "place_id": "poi-1",
                        "name": "Clinic",
                        "categories": ["healthcare.clinic"],
                    },
                    "geometry": {"type": "Point", "coordinates": [12.5, 41.9]},
                }
            ]
        }

    provider = GeoapifyProvider(api_key="geoapify-test", fetcher=fetcher)
    request = ProviderRequest(
        capability_id="geoapify_amenities",
        bbox=(12.0, 41.0, 13.0, 42.0),
        params={"live": True, "categories": "healthcare"},
    )

    first = asyncio.run(provider.fetch(request))
    second = asyncio.run(provider.fetch(request))

    assert first.payload == second.payload
    assert len(calls) == 1


###############################################################################
def test_geoapify_provider_returns_empty_result_for_empty_or_malformed_payloads() -> None:
    async def empty_fetcher(url: str, headers: dict[str, str] | None = None):
        return {"features": []}

    async def malformed_fetcher(url: str, headers: dict[str, str] | None = None):
        return {"features": [{"properties": {"name": "Missing geometry"}}]}

    empty = asyncio.run(
        GeoapifyProvider(api_key="geoapify-test", fetcher=empty_fetcher).fetch(
            ProviderRequest(
                capability_id="geoapify_amenities",
                bbox=(12.0, 41.0, 13.0, 42.0),
                params={"live": True},
            )
        )
    )
    malformed = asyncio.run(
        GeoapifyProvider(api_key="geoapify-test", fetcher=malformed_fetcher).fetch(
            ProviderRequest(
                capability_id="geoapify_amenities",
                bbox=(12.0, 41.0, 13.0, 42.0),
                params={"live": True},
            )
        )
    )

    assert empty.payload["features"] == []
    assert empty.payload["totalResults"] == 0
    assert malformed.payload["features"] == []
    assert malformed.payload["totalResults"] == 0


###############################################################################
def test_nasa_gibs_provider_returns_wms_descriptor() -> None:
    response = asyncio.run(
        NASAGIBSProvider().fetch(
            ProviderRequest(
                capability_id="VIIRS_SNPP_CorrectedReflectance_TrueColor",
                params={"crs": "EPSG:4326", "time": "2026-05-10"},
            )
        )
    )

    assert response.payload["renderingMode"] == "wms"
    assert response.payload["crs"] == "EPSG:4326"
    assert response.attribution


###############################################################################
def test_nasa_gibs_provider_live_validation_uses_stale_cache() -> None:
    clock = 0.0

    def now() -> float:
        return clock

    async def ok_fetcher(url: str, headers: dict[str, str] | None = None):
        return {"service": "WMS", "layers": ["VIIRS_SNPP_CorrectedReflectance_TrueColor"]}

    provider = NASAGIBSProvider(
        fetcher=ok_fetcher,
        cache=GeospatialCache(clock=now),
        cache_ttl_seconds=1,
        stale_while_revalidate_seconds=10,
    )
    request = ProviderRequest(
        capability_id="VIIRS_SNPP_CorrectedReflectance_TrueColor",
        params={"live_validate": True},
    )
    first = asyncio.run(provider.fetch(request))

    async def timeout_fetcher(url: str, headers: dict[str, str] | None = None):
        raise TimeoutError("timed out")

    clock = 2.0
    provider.fetcher = timeout_fetcher
    stale = asyncio.run(provider.fetch(request))

    assert first.payload["liveValidation"]["service"] == "WMS"
    assert stale.stale is True
    assert stale.payload["liveValidation"]["layers"] == [
        "VIIRS_SNPP_CorrectedReflectance_TrueColor"
    ]


###############################################################################
def test_nasa_gibs_provider_rejects_malformed_live_validation_without_cache() -> None:
    async def malformed_fetcher(url: str, headers: dict[str, str] | None = None):
        return ["not", "metadata"]

    with pytest.raises(ProviderUnavailableError):
        asyncio.run(
            NASAGIBSProvider(fetcher=malformed_fetcher).fetch(
                ProviderRequest(
                    capability_id="VIIRS_SNPP_CorrectedReflectance_TrueColor",
                    params={"live_validate": True},
                )
            )
        )


###############################################################################
def test_arcgis_rest_provider_builds_geojson_query_url() -> None:
    response = asyncio.run(
        ArcGISRestProvider().fetch(
            ProviderRequest(
                capability_id="arcgis_layer",
                bbox=(-1.0, 2.0, 3.0, 4.0),
                params={"service_url": "https://example.test/FeatureServer/0/query"},
            )
        )
    )

    assert response.payload["renderingMode"] == "geojson"
    assert "f=geojson" in response.payload["featuresUrl"]
    assert "geometry=-1.0%2C2.0%2C3.0%2C4.0" in response.payload["featuresUrl"]


###############################################################################
def test_census_provider_selects_demographic_choropleth() -> None:
    response = asyncio.run(
        CensusProvider().fetch(
            ProviderRequest(
                capability_id="census_tigerweb_demographics",
                bbox=(-78.0, 38.0, -77.0, 39.0),
            )
        )
    )

    assert response.provider_id == "census"
    assert response.payload["renderingMode"] == "choropleth"
    assert "tigerweb.geo.census.gov" in response.payload["featuresUrl"]


###############################################################################
def test_windy_webcams_live_fetch_normalizes_camera_metadata() -> None:
    calls: list[tuple[str, dict[str, str] | None]] = []

    async def fetcher(url: str, headers: dict[str, str] | None = None):
        calls.append((url, headers))
        return {
            "webcams": [
                {
                    "webcamId": "cam-1",
                    "title": "Pass view",
                    "location": {"latitude": 45.1, "longitude": 7.2},
                    "images": {"current": {"url": "https://example.test/preview.jpg"}},
                    "urls": {"detail": "https://example.test/cam"},
                    "player": {"day": {"url": "https://example.test/player"}},
                }
            ]
        }

    response = asyncio.run(
        WindyWebcamsProvider(api_key="windy-test", fetcher=fetcher).fetch(
            ProviderRequest(
                capability_id="windy_webcams",
                bbox=(7.0, 45.0, 7.5, 45.5),
                params={"live": True},
            )
        )
    )

    assert calls[0][1] == {"x-windy-api-key": "windy-test"}
    assert "bbox=7.0,45.0,7.5,45.5" in calls[0][0]
    assert response.payload["renderingMode"] == "camera-points"
    assert response.payload["features"][0]["preview_image_url"].endswith("preview.jpg")
    assert response.payload["features"][0]["embedding_allowed"] is False


###############################################################################
def test_windy_webcams_requires_key() -> None:
    with pytest.raises(ProviderAuthError):
        asyncio.run(
            WindyWebcamsProvider().fetch(
                ProviderRequest(capability_id="windy_webcams", params={"live": True})
            )
        )


###############################################################################
def test_windy_webcams_omits_expired_preview_and_detects_stale_camera() -> None:
    async def fetcher(url: str, headers: dict[str, str] | None = None):
        return {
            "webcams": [
                {
                    "webcamId": "cam-1",
                    "title": "Old pass view",
                    "location": {"latitude": 45.1, "longitude": 7.2},
                    "images": {
                        "current": {
                            "url": "https://example.test/expired.jpg",
                            "expiresAt": "2000-01-01T00:00:00Z",
                        }
                    },
                    "urls": {"detail": "https://example.test/cam"},
                    "lastUpdatedOn": "2000-01-01T00:00:00Z",
                }
            ]
        }

    response = asyncio.run(
        WindyWebcamsProvider(api_key="windy-test", fetcher=fetcher).fetch(
            ProviderRequest(capability_id="windy_webcams", params={"live": True})
        )
    )

    feature = response.payload["features"][0]
    assert feature["preview_image_url"] is None
    assert feature["stale"] is True
    assert feature["metadata"]["preview_expired"] is True


###############################################################################
def test_windy_webcams_embeds_only_when_explicitly_allowed() -> None:
    async def fetcher(url: str, headers: dict[str, str] | None = None):
        return {
            "webcams": [
                {
                    "webcamId": "cam-1",
                    "title": "Embeddable pass view",
                    "location": {"latitude": 45.1, "longitude": 7.2},
                    "urls": {"detail": "https://example.test/cam"},
                    "player": {
                        "embeddingAllowed": True,
                        "day": {"url": "https://example.test/player"},
                    },
                },
                {
                    "webcamId": "cam-2",
                    "title": "Official link only",
                    "location": {"latitude": 45.2, "longitude": 7.3},
                    "urls": {"detail": "https://example.test/cam-2"},
                    "player": {"day": {"url": "https://example.test/player-2"}},
                },
            ]
        }

    response = asyncio.run(
        WindyWebcamsProvider(api_key="windy-test", fetcher=fetcher).fetch(
            ProviderRequest(capability_id="windy_webcams", params={"live": True})
        )
    )

    allowed, denied = response.payload["features"]
    assert allowed["embedding_allowed"] is True
    assert allowed["embed_url"] == "https://example.test/player"
    assert denied["embedding_allowed"] is False
    assert denied["embed_url"] is None


###############################################################################
def test_windy_webcams_returns_stale_cache_after_live_failure() -> None:
    async def first_fetcher(url: str, headers: dict[str, str] | None = None):
        return {
            "webcams": [
                {
                    "id": "cam-1",
                    "name": "Cached camera",
                    "latitude": 45.1,
                    "longitude": 7.2,
                    "url": "https://example.test/cam",
                }
            ]
        }

    provider = WindyWebcamsProvider(api_key="windy-test", fetcher=first_fetcher)
    asyncio.run(
        provider.fetch(
            ProviderRequest(capability_id="windy_webcams", params={"live": True})
        )
    )

    async def failing_fetcher(url: str, headers: dict[str, str] | None = None):
        raise RuntimeError("network down")

    provider.fetcher = failing_fetcher
    stale = asyncio.run(
        provider.fetch(
            ProviderRequest(capability_id="windy_webcams", params={"live": True})
        )
    )

    assert stale.stale is True
    assert stale.payload["features"][0]["name"] == "Cached camera"
    assert stale.warnings
