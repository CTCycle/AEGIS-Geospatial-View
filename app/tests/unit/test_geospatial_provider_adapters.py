from __future__ import annotations
from tests.conftest import run_async_in_thread
import pytest
import time
import httpx
from server.services.geospatial.cache import GeospatialCache
from server.services.geospatial.provider_registry import ProviderRegistry
from server.services.geospatial.overpass import OverpassInvalidQueryError, OverpassRateLimitError, OverpassRequestError
from server.services.geospatial.providers.base import ProviderAuthError, ProviderInvalidQueryError, ProviderRateLimitError, ProviderRequest, ProviderUnavailableError, FeatureRequest, ProviderResponse, ProviderResult, provider_cache_key, response_without_credentials, safe_request_params, ProviderMalformedPayloadError
from server.services.geospatial.providers.arcgis_rest import ArcGISRestProvider
from server.services.geospatial.providers.census import CensusProvider
from server.services.geospatial.providers.nasa_gibs import NASAGIBSProvider
from server.services.geospatial.providers.openaq import OpenAQProvider
from server.services.geospatial.providers.openmeteo import OpenMeteoProvider
from server.services.geospatial.providers.overpass import OverpassProvider
from server.services.geospatial.providers.pvgis import PVGISProvider
from server.services.geospatial.providers.tomtom import TomTomProvider, build_tomtom_tile_url
from server.services.geospatial.providers.windy_webcams import WindyWebcamsProvider
from server.services.agent.capability_execution import _response_summary, CapabilityExecutionService, ToolExecutionContext
from server.services.geospatial.providers.openchargemap import OpenChargeMapProvider
from server.services.geospatial.providers.opentripmap import OpenTripMapProvider
from server.services.geospatial.providers.ourairports import OurAirportsProvider
from server.services.geospatial.providers.nominatim import NominatimProvider
from server.services.geospatial.providers.mobility_database import MobilityDatabaseProvider
from urllib.parse import parse_qs, urlsplit
from server.services.geospatial.openaq import OpenAQRequestError, OpenAQService
from server.services.geospatial.providers import http as provider_http
from server.services.geospatial.providers.local_open_data import LocalOpenDataProvider
from server.services.geospatial.providers.noaa import NOAAProvider

# --- test_geospatial_provider_adapters_core.py ---




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


GIBS_WMTS_XML = """<?xml version="1.0"?>
<Capabilities xmlns="http://www.opengis.net/wmts/1.0" xmlns:ows="http://www.opengis.net/ows/1.1">
  <Contents>
    <Layer>
      <ows:Title>VIIRS true color</ows:Title>
      <ows:Identifier>VIIRS_SNPP_CorrectedReflectance_TrueColor</ows:Identifier>
      <Style isDefault="true"><ows:Identifier>default</ows:Identifier></Style>
      <Format>image/png</Format>
      <Dimension>
        <ows:Identifier>Time</ows:Identifier>
        <Default>2026-05-10</Default>
        <Value>2026-05-01/2026-05-10/P1D</Value>
      </Dimension>
      <TileMatrixSetLink><TileMatrixSet>GoogleMapsCompatible_Level9</TileMatrixSet></TileMatrixSetLink>
    </Layer>
  </Contents>
</Capabilities>
"""


GIBS_WMS_XML = """<?xml version="1.0"?>
<WMS_Capabilities xmlns="http://www.opengis.net/wms">
  <Capability>
    <Request><GetMap><Format>image/png</Format></GetMap></Request>
    <Layer>
      <Layer queryable="0">
        <Name>VIIRS_SNPP_CorrectedReflectance_TrueColor</Name>
        <Title>VIIRS true color WMS</Title>
        <CRS>EPSG:3857</CRS>
        <Style><Name>default</Name></Style>
        <Dimension name="time" default="2026-05-10">2026-05-01/2026-05-10/P1D</Dimension>
      </Layer>
    </Layer>
  </Capability>
</WMS_Capabilities>
"""

###############################################################################
async def _gibs_capabilities_fetcher(url: str, headers: dict[str, str] | None = None):
    del headers
    return GIBS_WMTS_XML if "wmts" in url else GIBS_WMS_XML

###############################################################################
def test_openmeteo_provider_selects_weather_or_air_quality() -> None:
    provider = OpenMeteoProvider(service=_OpenMeteoService())  # type: ignore[arg-type]

    weather = run_async_in_thread(
        provider.fetch(
            ProviderRequest(
                capability_id="openmeteo_weather_forecast",
                params={"latitude": 41.9, "longitude": 12.5},
            )
        )
    )
    air = run_async_in_thread(
        provider.fetch(
            ProviderRequest(
                capability_id="openmeteo_air_quality_forecast",
                params={"latitude": 41.9, "longitude": 12.5},
            )
        )
    )

    assert weather.payload["kind"] == "weather_forecast"
    assert weather.payload["renderingMode"] == "clustered-points"
    assert air.payload["kind"] == "air_quality_forecast"
    assert air.payload["renderingMode"] == "clustered-points"
    assert air.payload["features"][0]["metadata"]["pollutantSymbols"]["pm25"] == 8

###############################################################################
def test_openmeteo_provider_returns_wind_arrow_features() -> None:
    provider = OpenMeteoProvider(service=_OpenMeteoService())  # type: ignore[arg-type]

    response = run_async_in_thread(
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
def test_openmeteo_provider_preserves_zero_measurements() -> None:

    ###############################################################################
    class _ZeroWeatherService(_OpenMeteoService):

        # -------------------------------------------------------------------------
        async def get_weather_forecast(self, *, latitude: float, longitude: float):
            return {
                "kind": "weather_forecast",
                "latitude": latitude,
                "longitude": longitude,
                "current": {
                    "relative_humidity_2m": 0,
                    "surface_pressure": 0,
                    "wind_speed_10m": 0,
                    "wind_direction_10m": 0,
                    "wind_gusts_10m": 0,
                },
                "hourly_preview": [{"time": "2026-05-11T00:00"}],
                "result_status": "partial",
                "partial": True,
                "source_url": "https://weather.example/forecast",
            }

    response = run_async_in_thread(
        OpenMeteoProvider(service=_ZeroWeatherService()).fetch(  # type: ignore[arg-type]
            ProviderRequest(
                capability_id="openmeteo_pressure_humidity_wind",
                params={"latitude": 43.817, "longitude": 7.777},
            )
        )
    )

    feature = response.payload["features"][0]
    assert feature["relative_humidity_2m"] == 0
    assert feature["metadata"]["humidity"] == 0
    assert feature["surface_pressure"] == 0
    assert feature["metadata"]["windArrow"] == {"speed": 0, "direction": 0}
    assert response.result_status == "partial"

###############################################################################
def test_openmeteo_provider_preserves_hourly_forecast_alongside_map_feature() -> None:
    forecast = [
        {"time": f"2026-05-11T{hour:02d}:00", "temperature_2m": 18 + hour}
        for hour in range(24)
    ]

    ###############################################################################
    class _HourlyWeatherService(_OpenMeteoService):

        # -------------------------------------------------------------------------
        async def get_weather_forecast(self, *, latitude: float, longitude: float):
            return {
                "kind": "weather_forecast",
                "latitude": latitude,
                "longitude": longitude,
                "hourly_preview": forecast[:6],
                "hourly_forecast": forecast,
                "result_status": "ok",
                "partial": False,
            }

    response = run_async_in_thread(
        OpenMeteoProvider(service=_HourlyWeatherService()).fetch(  # type: ignore[arg-type]
            ProviderRequest(
                capability_id="get_weather_forecast",
                params={"latitude": 41.9, "longitude": 12.5},
            )
        )
    )

    assert response.payload["hourlyForecast"] == forecast
    assert len(response.payload["features"]) == 1


###############################################################################
def test_overpass_provider_normalizes_poi_features_from_bbox() -> None:
    service = _OverpassService()
    provider = OverpassProvider(service=service)  # type: ignore[arg-type]

    response = run_async_in_thread(
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

    run_async_in_thread(
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
def test_overpass_provider_maps_nested_specific_category_to_service_filter() -> None:
    service = _OverpassService()
    provider = OverpassProvider(service=service)  # type: ignore[arg-type]

    run_async_in_thread(
        provider.fetch(
            ProviderRequest(
                capability_id="overpass_poi_amenities",
                bbox=(12.0, 41.0, 13.0, 42.0),
                params={"filters": {"category": "pharmacy"}},
            )
        )
    )

    assert service.calls[0]["amenity_tags"] is None
    assert service.calls[0]["categories"] == ["pharmacy"]

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
        run_async_in_thread(
            OverpassProvider(service=_RateLimitedService()).fetch(  # type: ignore[arg-type]
                ProviderRequest(
                    capability_id="overpass_poi_amenities",
                    bbox=(12.0, 41.0, 13.0, 42.0),
                )
            )
        )
    with pytest.raises(ProviderUnavailableError):
        run_async_in_thread(
            OverpassProvider(service=_TimeoutService()).fetch(  # type: ignore[arg-type]
                ProviderRequest(
                    capability_id="overpass_poi_amenities",
                    bbox=(12.0, 41.0, 13.0, 42.0),
                )
            )
        )

###############################################################################
def test_overpass_provider_distinguishes_invalid_query_from_transport_failure() -> None:

    ###############################################################################
    class _InvalidQueryService(_OverpassService):

        # -------------------------------------------------------------------------
        async def get_nearby_poi(self, **kwargs):  # noqa: ANN003
            raise OverpassInvalidQueryError("unsupported category")

    with pytest.raises(ProviderInvalidQueryError):
        run_async_in_thread(
            OverpassProvider(service=_InvalidQueryService()).fetch(  # type: ignore[arg-type]
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

    response = run_async_in_thread(
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

    response = run_async_in_thread(
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
        run_async_in_thread(
            OpenAQProvider(service=_OpenAQService()).fetch(  # type: ignore[arg-type]
                ProviderRequest(capability_id="openaq_air_quality")
            )
        )

###############################################################################
def test_openaq_provider_filters_pollutants() -> None:
    response = run_async_in_thread(
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

    response = run_async_in_thread(
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

    first = run_async_in_thread(provider.fetch(request))
    second = run_async_in_thread(provider.fetch(request))
    clock = 2.0
    provider.service = _FailingOpenAQService()  # type: ignore[assignment]
    stale = run_async_in_thread(provider.fetch(request))

    assert first.payload == second.payload
    assert len(service.calls) == 1
    assert stale.stale is True
    assert stale.payload["features"][0]["name"] == "Station"
    assert stale.warnings

###############################################################################
def test_pvgis_provider_returns_metadata_only_analysis() -> None:
    provider = PVGISProvider(service=_PVGISService())  # type: ignore[arg-type]

    response = run_async_in_thread(
        provider.fetch(
            ProviderRequest(
                capability_id="pvgis_solar",
                params={"latitude": 41.9, "longitude": 12.5},
            )
        )
    )

    assert response.payload["renderingMode"] == "metadata-only"
    assert response.payload["yearlyKwhPerKwpEstimate"] == 1234.5
    assert response.result_type == "metadata"
    assert response.result_status == "ok"

###############################################################################
def test_tomtom_requires_keys_before_emitting_urls() -> None:
    with pytest.raises(ProviderAuthError):
        run_async_in_thread(
            TomTomProvider().fetch(ProviderRequest(capability_id="tomtom_traffic_flow"))
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

    response = run_async_in_thread(
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
    response = run_async_in_thread(
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
def test_provider_registry_ignores_environment_keys_for_gated_adapters(
    monkeypatch,
) -> None:
    monkeypatch.setenv("TOMTOM_API_KEY", "tomtom-test")
    registry = ProviderRegistry()
    registry.build_from_manifests()

    assert getattr(registry.get("tomtom"), "api_key") == ""
    with pytest.raises(ProviderAuthError, match="API key is required"):
        run_async_in_thread(
            registry.fetch(
                "tomtom", ProviderRequest(capability_id="tomtom_traffic_flow")
            )
        )

###############################################################################
def test_nasa_gibs_provider_returns_wms_descriptor() -> None:
    response = run_async_in_thread(
        NASAGIBSProvider(fetcher=_gibs_capabilities_fetcher).fetch(
            ProviderRequest(
                capability_id="VIIRS_SNPP_CorrectedReflectance_TrueColor",
                params={"crs": "EPSG:4326", "time": "2026-05-10"},
            )
        )
    )

    assert response.payload["layer"]["rendering_mode"] == "wmts"
    assert response.payload["render"]["rendering_mode"] == "wmts"
    assert (
        response.payload["render"]["tile_matrix_set"] == "GoogleMapsCompatible_Level9"
    )
    assert response.attribution

###############################################################################
def test_arcgis_rest_provider_builds_geojson_query_url() -> None:
    response = run_async_in_thread(
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
    response = run_async_in_thread(
        CensusProvider().fetch(
            ProviderRequest(
                capability_id="census_tigerweb_demographics",
                bbox=(-78.0, 38.0, -77.0, 39.0),
            )
        )
    )

    assert response.provider_id == "census"
    assert response.payload["renderingMode"] == "choropleth"
    assert response.payload["status"] == "server-side-only"
    assert "featuresUrl" not in response.payload

###############################################################################
def test_census_cartographic_query_caps_records_and_generalizes_to_bbox_span() -> None:
    response = run_async_in_thread(
        CensusProvider().fetch(
            ProviderRequest(
                capability_id="census_cartographic_boundaries",
                bbox=(-87.94, 41.64, -87.52, 42.02),
            )
        )
    )

    url = response.payload["featuresUrl"]
    assert "resultRecordCount=2000" in url
    assert "maxAllowableOffset=0.000420" in url

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

    response = run_async_in_thread(
        WindyWebcamsProvider(api_key="windy-test", fetcher=fetcher).fetch(
            ProviderRequest(
                capability_id="windy_webcams",
                bbox=(7.0, 45.0, 7.5, 45.5),
                params={"live": True},
            )
        )
    )

    assert calls[0][1] == {"x-windy-api-key": "windy-test"}
    assert "bbox=45.5,7.5,45.0,7.0" in calls[0][0]
    assert response.payload["renderingMode"] == "camera-points"
    assert response.payload["features"][0]["preview_image_url"].endswith("preview.jpg")
    assert response.payload["features"][0]["embedding_allowed"] is False

###############################################################################
def test_windy_webcams_requires_key() -> None:
    with pytest.raises(ProviderAuthError):
        run_async_in_thread(
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

    response = run_async_in_thread(
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

    response = run_async_in_thread(
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
    run_async_in_thread(
        provider.fetch(
            ProviderRequest(capability_id="windy_webcams", params={"live": True})
        )
    )

    async def failing_fetcher(url: str, headers: dict[str, str] | None = None):
        raise RuntimeError("network down")

    provider.fetcher = failing_fetcher
    stale = run_async_in_thread(
        provider.fetch(
            ProviderRequest(capability_id="windy_webcams", params={"live": True})
        )
    )

    assert stale.stale is True
    assert stale.payload["features"][0]["name"] == "Cached camera"
    assert stale.warnings

# --- test_geospatial_optional_provider_adapters.py ---




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

# --- test_geospatial_provider_contracts.py ---



###############################################################################
class _FeatureOnlyProvider:
    provider_id = "feature_only"

    # -------------------------------------------------------------------------
    async def fetch_features(self, request: FeatureRequest) -> ProviderResult:
        return ProviderResult(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={"api_key": "should-not-leak", "value": 1},
            attribution=["Example Attribution"],
        )

    # -------------------------------------------------------------------------
    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        raise AssertionError("fetch_features should be preferred")

###############################################################################
def test_provider_registry_prefers_canonical_fetch_features_contract() -> None:
    registry = ProviderRegistry(providers=[_FeatureOnlyProvider()])

    response = run_async_in_thread(
        registry.fetch("feature_only", FeatureRequest(capability_id="sample"))
    )

    assert response.payload == {"api_key": "<redacted>", "value": 1}
    assert response.attribution == ["Example Attribution"]

###############################################################################
def test_provider_cache_key_uses_safe_stable_request_parts() -> None:
    request = FeatureRequest(
        capability_id="layer",
        bbox=(-1.0, 2.0, 3.0, 4.0),
        zoom=8,
        params={"category": "hospital", "api_key": "secret"},
    )

    key_a = provider_cache_key("Provider", request)
    key_b = provider_cache_key("provider", request)

    assert key_a == key_b
    assert "secret" not in key_a
    assert key_a.startswith("provider:layer:")

###############################################################################
def test_safe_request_params_redacts_credentials() -> None:
    params = safe_request_params(
        {"token": "abc", "authorization": "Bearer abc", "category": "parks"}
    )

    assert params == {
        "authorization": "<redacted>",
        "category": "parks",
        "token": "<redacted>",
    }

###############################################################################
def test_response_redaction_preserves_map_url_template_tokens() -> None:
    response = response_without_credentials(
        ProviderResponse(
            capability_id="fema_nfhl_flood_zones",
            provider_id="fema",
            payload={
                "tileUrl": (
                    "https://hazards.example/export?"
                    "bbox={bbox-epsg-3857}&format=png32"
                )
            },
        )
    )

    assert response.payload["tileUrl"] == (
        "https://hazards.example/export?"
        "bbox={bbox-epsg-3857}&format=png32"
    )

###############################################################################
def test_nominatim_provider_geocodes_live_contract_payload() -> None:
    async def fetcher(url: str, headers: dict[str, str] | None = None):
        assert "q=Rome" in url
        assert headers and "User-Agent" in headers
        return [
            {
                "place_id": 1,
                "display_name": "Rome, Roma Capitale, Lazio, Italy",
                "lat": "41.8933",
                "lon": "12.4829",
                "type": "city",
            }
        ]

    response = run_async_in_thread(
        NominatimProvider(fetcher=fetcher).fetch(
            ProviderRequest(
                capability_id="location_to_coordinates",
                params={"query": "Rome"},
            )
        )
    )

    assert response.payload["resultCount"] == 1
    assert response.payload["results"][0]["latitude"] == 41.8933

###############################################################################
def test_mobility_database_provider_searches_local_snapshot(tmp_path) -> None:
    catalog = tmp_path / "feeds.csv"
    catalog.write_text(
        "mdb_source_id,provider,name,urls.latest,urls.license,urls.authentication_type\n"
        "f-test,Example Transit,Example Transit,https://agency.example/gtfs.zip,https://agency.example/license,1\n",
        encoding="utf-8",
    )
    response = run_async_in_thread(
        MobilityDatabaseProvider(catalog_path=catalog).fetch(
            ProviderRequest(
                capability_id="mobility_database_feeds", params={"query": "Example"}
            )
        )
    )

    assert response.payload["feedCount"] == 1
    assert response.payload["feeds"][0]["staticFeedUrl"].endswith("gtfs.zip")
    assert response.payload["feeds"][0]["authentication"]["required"] is True


###############################################################################
def test_mobility_database_default_cache_uses_canonical_cache_root(monkeypatch, tmp_path) -> None:
    cache_root = tmp_path / "canonical-cache"
    monkeypatch.setenv("AEGIS_CACHE_ROOT", str(cache_root))
    monkeypatch.delenv("AEGIS_MOBILITY_DATABASE_CATALOG_PATH", raising=False)

    provider = MobilityDatabaseProvider()

    assert provider.catalog_path == cache_root / "mobility-database" / "feeds_v2.csv"

# --- test_geospatial_provider_hardening.py ---





###############################################################################
def test_shared_http_rejects_redirects_and_limits_response_bytes(monkeypatch) -> None:

    ###############################################################################
    class _Response:
        status_code = 200
        headers = {"content-length": "4"}

        # -------------------------------------------------------------------------
        async def __aenter__(self):
            return self

        # -------------------------------------------------------------------------
        async def __aexit__(self, *args):
            return None

        # -------------------------------------------------------------------------
        async def aiter_bytes(self):
            yield b"1234"

    ###############################################################################
    class _Client:

        # -------------------------------------------------------------------------
        def stream(self, *args, **kwargs):
            return _Response()

    monkeypatch.setattr(provider_http, "_ASYNC_HTTP_CLIENT", _Client())
    with pytest.raises(ProviderUnavailableError, match="size limit"):
        run_async_in_thread(
            provider_http.fetch_bytes_url("https://example.test/data", max_bytes=3)
        )

    with pytest.raises(ProviderUnavailableError, match="redirect"):
        provider_http._raise_for_status(
            httpx.Response(302, headers={"location": "/next"})
        )

###############################################################################
def test_shared_http_uses_scoped_remaining_timeout(monkeypatch) -> None:
    timeouts: list[float | None] = []

    ###############################################################################
    class _Response:
        status_code = 200
        headers = {"content-length": "2"}

        # -------------------------------------------------------------------------
        async def __aenter__(self):
            return self

        # -------------------------------------------------------------------------
        async def __aexit__(self, *args):
            return None

        # -------------------------------------------------------------------------
        async def aiter_bytes(self):
            yield b"ok"

    ###############################################################################
    class _Client:

        # -------------------------------------------------------------------------
        def stream(self, *args, **kwargs):
            timeouts.append(kwargs.get("timeout"))
            return _Response()

    async def _fetch() -> bytes:
        with provider_http.request_timeout_scope(0.37):
            return await provider_http.fetch_bytes_url("https://example.test/data")

    monkeypatch.setattr(provider_http, "_ASYNC_HTTP_CLIENT", _Client())
    assert run_async_in_thread(_fetch()) == b"ok"
    assert timeouts == [pytest.approx(0.37)]

###############################################################################
def test_shared_http_preserves_retry_after_without_exposing_headers() -> None:
    with pytest.raises(ProviderRateLimitError) as error:
        provider_http._raise_for_status(
            httpx.Response(429, headers={"retry-after": "7"})
        )

    assert error.value.retry_after_seconds == 7.0
    assert "retry-after" not in str(error.value).lower()

###############################################################################
def test_openaq_v3_joins_location_sensors_to_latest_measurements() -> None:
    calls: list[tuple[str, dict[str, str]]] = []

    def requester(url: str, headers: dict[str, str]):
        calls.append((url, headers))
        if "/locations/42/latest" in url:
            return {
                "results": [
                    {
                        "locationsId": 42,
                        "sensorsId": 9001,
                        "value": 8.5,
                        "datetime": {"utc": "2026-08-27T10:00:00Z"},
                        "coordinates": {"latitude": 41.9, "longitude": 12.5},
                    }
                ]
            }
        return {
            "results": [
                {
                    "id": 42,
                    "name": "Roma station",
                    "coordinates": {"latitude": 41.9, "longitude": 12.5},
                    "instruments": [
                        {
                            "sensors": [
                                {
                                    "id": 9001,
                                    "parameter": {"name": "pm2.5", "units": "µg/m³"},
                                }
                            ]
                        }
                    ],
                }
            ]
        }

    response = run_async_in_thread(
        OpenAQService(api_key="secret", requester=requester).get_nearby_measurements(
            41.9, 12.5, 5000
        )
    )

    assert response["locations"][0]["measurements"]["pm25"]["value"] == 8.5
    assert len(calls) == 2
    assert "order_by=id" in calls[0][0]
    assert "radius=5000" in calls[0][0]
    assert all("secret" not in url for url, _ in calls)
    assert all(headers["X-API-Key"] == "secret" for _, headers in calls)

###############################################################################
def test_openaq_request_failure_is_not_converted_to_empty_data() -> None:
    def requester(url: str, headers: dict[str, str]):
        raise OpenAQRequestError("OpenAQ request failed.")

    with pytest.raises(OpenAQRequestError):
        run_async_in_thread(
            OpenAQService(
                api_key="secret", requester=requester
            ).get_nearby_measurements(41.9, 12.5)
        )

###############################################################################
def test_noaa_coops_discovers_stations_and_requests_station_observations() -> None:
    calls: list[str] = []

    async def fetcher(url: str, headers=None):  # noqa: ANN001
        calls.append(url)
        if "stations.json" in url:
            return {
                "stations": [
                    {
                        "id": "9414290",
                        "name": "San Francisco",
                        "lat": 37.8,
                        "lng": -122.5,
                    }
                ]
            }
        query = parse_qs(urlsplit(url).query)
        assert query["station"] == ["9414290"]
        assert query["product"] == ["water_level"]
        assert query["datum"] == ["MLLW"]
        return {"data": [{"t": "2026-08-27 10:00", "v": "1.25"}]}

    response = run_async_in_thread(
        NOAAProvider(fetcher=fetcher).fetch(
            ProviderRequest(
                capability_id="noaa_coops_water_levels",
                bbox=(-123.0, 37.0, -122.0, 38.0),
                params={"live": True},
            )
        )
    )

    assert len(calls) == 2
    assert response.payload["features"][0]["id"] == "9414290"
    assert response.payload["features"][0]["value"] == 1.25

###############################################################################
def test_census_demographics_discovers_boundary_layer_and_joins_acs() -> None:
    calls: list[str] = []

    async def fetcher(url: str, headers=None):  # noqa: ANN001
        calls.append(url)
        if url.endswith("Tracts_Blocks/MapServer?f=json"):
            return {
                "layers": [
                    {"id": 3, "name": "ACS 2024", "subLayerIds": [4]},
                ]
            }
        if url.endswith("Tracts_Blocks/MapServer/3?f=json"):
            return {"layers": [{"id": 4, "name": "Census Tracts"}]}
        if "/MapServer/4/query" in url:
            return {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "id": "tract-1",
                        "properties": {"GEOID": "06001400100"},
                        "geometry": {"type": "Polygon", "coordinates": []},
                    }
                ],
            }
        if "api.census.gov/data/2024/acs/acs5" in url:
            return [
                ["NAME", "B01003_001E", "state", "county", "tract"],
                ["Test tract", "1234", "06", "001", "400100"],
            ]
        raise AssertionError(f"Unexpected Census URL: {url}")

    response = run_async_in_thread(
        CensusProvider(fetcher=fetcher).fetch(
            ProviderRequest(
                capability_id="census_tigerweb_demographics",
                bbox=(-123.0, 37.0, -122.0, 38.0),
                params={"live": True, "vintage": "2024"},
            )
        )
    )

    feature = response.payload["features"][0]
    assert response.payload["boundaryLayerId"] == "4"
    assert response.payload["joinCount"] == 1
    assert feature["properties"]["population"] == 1234
    assert any("api.census.gov/data/2024" in url for url in calls)

###############################################################################
def test_local_open_data_requires_configured_source_id_and_preserves_geojson_mode() -> (
    None
):
    async def fetcher(url: str, headers=None):  # noqa: ANN001
        return {
            "type": "FeatureCollection",
            "features": [{"type": "Feature", "properties": {}, "geometry": None}],
        }

    provider = LocalOpenDataProvider(
        source_map={"local_parcels": "https://agency.example/parcels.json"},
        fetcher=fetcher,
    )
    with pytest.raises(ProviderInvalidQueryError):
        run_async_in_thread(
            provider.fetch(
                ProviderRequest(
                    capability_id="local_parcels",
                    params={"source_url": "https://attacker.example/metadata.json"},
                )
            )
        )

    response = run_async_in_thread(
        provider.fetch(ProviderRequest(capability_id="local_parcels"))
    )
    assert response.payload["renderingMode"] == "geojson"
    assert response.payload["sourceId"] == "local_parcels"

###############################################################################
@pytest.mark.parametrize(
    ("provider_error", "expected_code"),
    [
        (ProviderAuthError("missing"), "provider_authentication"),
        (ProviderRateLimitError("limited"), "provider_rate_limit"),
        (ProviderInvalidQueryError("invalid"), "provider_invalid_query"),
        (ProviderMalformedPayloadError("malformed"), "provider_malformed_response"),
        (ProviderUnavailableError("unavailable"), "provider_unavailable"),
    ],
)
def test_native_tool_maps_provider_failures_to_canonical_codes(
    provider_error: Exception, expected_code: str
) -> None:
    service = object.__new__(CapabilityExecutionService)
    result = service._provider_failure(
        context=ToolExecutionContext(
            conversation_id="conversation-1",
            call_id="call-1",
        ),
        capability_id="provider-capability",
        provider_id="provider",
        started=time.perf_counter(),
        error=provider_error,
    )

    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == expected_code
