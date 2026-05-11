from __future__ import annotations

import asyncio

import pytest

from server.services.geospatial.provider_registry import ProviderRegistry
from server.services.geospatial.providers.base import ProviderAuthError, ProviderRequest
from server.services.geospatial.providers.arcgis_rest import ArcGISRestProvider
from server.services.geospatial.providers.census import CensusProvider
from server.services.geospatial.providers.geoapify import GeoapifyProvider
from server.services.geospatial.providers.nasa_gibs import NASAGIBSProvider
from server.services.geospatial.providers.openaq import OpenAQProvider
from server.services.geospatial.providers.openmeteo import OpenMeteoProvider
from server.services.geospatial.providers.overpass import OverpassProvider
from server.services.geospatial.providers.pvgis import PVGISProvider
from server.services.geospatial.providers.tomtom import TomTomProvider


class _OpenMeteoService:
    async def get_weather_forecast(self, *, latitude: float, longitude: float):
        return {
            "kind": "weather_forecast",
            "latitude": latitude,
            "longitude": longitude,
            "timezone": "Europe/Rome",
            "current": {"temperature_2m": 18},
            "hourly_preview": [{"time": "2026-05-11T00:00", "temperature_2m": 18}],
            "resolved_at": "2026-05-11T00:00:00+00:00",
            "attribution": "Data from Open-Meteo",
        }

    async def get_air_quality_forecast(self, *, latitude: float, longitude: float):
        return {
            "kind": "air_quality_forecast",
            "latitude": latitude,
            "longitude": longitude,
            "timezone": "Europe/Rome",
            "hourly_preview": [{"time": "2026-05-11T00:00", "pm10": 12}],
            "resolved_at": "2026-05-11T00:00:00+00:00",
            "attribution": "Data from Open-Meteo",
        }


class _OverpassService:
    default_radius_m = 1000.0

    async def get_nearby_poi(self, **kwargs):  # noqa: ANN003
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


class _OpenAQService:
    default_radius_m = 25000.0

    async def get_nearby_measurements(self, *, lat: float, lon: float, radius_m: float):
        return {
            "locations": [
                {
                    "id": 10,
                    "name": "Station",
                    "latitude": lat,
                    "longitude": lon,
                    "measurements": {"pm25": {"value": 8.0, "unit": "ug/m3"}},
                    "distance_m": 120,
                }
            ],
            "summary": {"pm25": {"mean": 8.0}},
            "center": {"latitude": lat, "longitude": lon},
            "attribution": "OpenAQ",
        }


class _PVGISService:
    async def get_point_estimate(self, latitude: float, longitude: float):
        return {
            "latitude": latitude,
            "longitude": longitude,
            "yearly_kwh_per_kwp_estimate": 1234.5,
            "raw": {"monthly": []},
            "attribution": "PVGIS",
        }


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


def test_overpass_provider_normalizes_poi_features_from_bbox() -> None:
    provider = OverpassProvider(service=_OverpassService())  # type: ignore[arg-type]

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


def test_openaq_provider_returns_station_features() -> None:
    provider = OpenAQProvider(service=_OpenAQService())  # type: ignore[arg-type]

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

    assert "tomtom-test" in str(tomtom.payload["tileUrl"])
    assert "geoapify-test" in str(geoapify.payload["tileUrl"])


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
