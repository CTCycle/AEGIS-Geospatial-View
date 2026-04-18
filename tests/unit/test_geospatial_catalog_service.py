from __future__ import annotations

import asyncio

from AEGIS.server.services.geospatial.catalog import GeospatialCatalogService


class _OpenAQStub:
    async def get_nearby_measurements(
        self, latitude: float, longitude: float, radius_m: float
    ) -> dict[str, object]:
        return {
            "provider": "openaq",
            "latitude": latitude,
            "longitude": longitude,
            "radius_m": radius_m,
        }


class _PVGISStub:
    async def get_point_estimate(
        self, latitude: float, longitude: float
    ) -> dict[str, object]:
        return {
            "provider": "pvgis",
            "latitude": latitude,
            "longitude": longitude,
        }


class _OpenMeteoStub:
    async def get_weather_forecast(
        self, *, latitude: float, longitude: float
    ) -> dict[str, object]:
        return {
            "kind": "weather_forecast",
            "latitude": latitude,
            "longitude": longitude,
        }

    async def get_air_quality_forecast(
        self, *, latitude: float, longitude: float
    ) -> dict[str, object]:
        return {
            "kind": "air_quality_forecast",
            "latitude": latitude,
            "longitude": longitude,
        }


class _OverpassStub:
    async def get_nearby_poi(
        self,
        *,
        latitude: float,
        longitude: float,
        radius_m: float,
    ) -> dict[str, object]:
        return {
            "kind": "poi_amenities",
            "latitude": latitude,
            "longitude": longitude,
            "radius_m": radius_m,
            "total_results": 1,
            "items": [{"id": "1", "name": "Cafe", "amenity": "cafe"}],
        }


class _RainViewerStub:
    async def get_latest_radar_metadata(self) -> dict[str, object]:
        return {
            "kind": "precipitation_radar",
            "latest_time": 123456,
            "tile_url_template": "https://tilecache.rainviewer.com/path/{z}/{x}/{y}.png",
        }


def test_catalog_contains_expected_core_sections() -> None:
    service = GeospatialCatalogService(
        openaq_service=_OpenAQStub(),  # type: ignore[arg-type]
        pvgis_service=_PVGISStub(),  # type: ignore[arg-type]
        openmeteo_service=_OpenMeteoStub(),  # type: ignore[arg-type]
        overpass_service=_OverpassStub(),  # type: ignore[arg-type]
        rainviewer_service=_RainViewerStub(),  # type: ignore[arg-type]
    )

    catalog = service.list_catalog()

    assert "providers" in catalog
    assert "basemaps" in catalog
    assert "overlays" in catalog
    assert any(item["id"] == "openaq_air_quality" for item in catalog["overlays"])
    assert any(item["id"] == "pvgis_solar" for item in catalog["overlays"])


def test_resolve_overlays_ignores_unknown_entries() -> None:
    service = GeospatialCatalogService(
        openaq_service=_OpenAQStub(),  # type: ignore[arg-type]
        pvgis_service=_PVGISStub(),  # type: ignore[arg-type]
        openmeteo_service=_OpenMeteoStub(),  # type: ignore[arg-type]
        overpass_service=_OverpassStub(),  # type: ignore[arg-type]
        rainviewer_service=_RainViewerStub(),  # type: ignore[arg-type]
    )

    resolved = service.resolve_overlays(["openaq_air_quality", "unknown_overlay"])

    assert len(resolved) == 1
    assert resolved[0]["id"] == "openaq_air_quality"


def test_catalog_exposes_eea_esa_overlay_transport_metadata() -> None:
    service = GeospatialCatalogService(
        openaq_service=_OpenAQStub(),  # type: ignore[arg-type]
        pvgis_service=_PVGISStub(),  # type: ignore[arg-type]
        openmeteo_service=_OpenMeteoStub(),  # type: ignore[arg-type]
        overpass_service=_OverpassStub(),  # type: ignore[arg-type]
        rainviewer_service=_RainViewerStub(),  # type: ignore[arg-type]
    )

    overlays = service.list_catalog()["overlays"]
    lookup = {item["id"]: item for item in overlays}

    eea = lookup["eea_noise_2019"]
    assert eea["type"] == "wms"
    assert eea["layers"] == "0"
    assert eea["wms_version"] == "1.1.1"
    assert eea["wms_exceptions"] == "application/vnd.ogc.se_inimage"
    assert isinstance(eea["bounds"], list)
    assert len(eea["bounds"]) == 4

    esa = lookup["esa_worldcover"]
    assert esa["type"] == "wmts"
    assert esa["layer_id"] == "WORLDCOVER_2021_MAP"
    assert esa["tile_matrix_set"] == "EPSG:3857"
    assert esa["wmts_format"] == "image/png"
    assert esa["wmts_style"] == ""


def test_insights_are_cached_for_same_aoi() -> None:
    service = GeospatialCatalogService(
        openaq_service=_OpenAQStub(),  # type: ignore[arg-type]
        pvgis_service=_PVGISStub(),  # type: ignore[arg-type]
        openmeteo_service=_OpenMeteoStub(),  # type: ignore[arg-type]
        overpass_service=_OverpassStub(),  # type: ignore[arg-type]
        rainviewer_service=_RainViewerStub(),  # type: ignore[arg-type]
    )

    first = asyncio.run(
        service.fetch_insights(
            latitude=45.0,
            longitude=9.0,
            overlay_ids=["openaq_air_quality", "pvgis_solar"],
            radius_m=2500.0,
        )
    )
    second = asyncio.run(
        service.fetch_insights(
            latitude=45.0,
            longitude=9.0,
            overlay_ids=["pvgis_solar", "openaq_air_quality"],
            radius_m=2500.0,
        )
    )

    assert first == second
    assert "air_quality" in second
    assert "solar_potential" in second


def test_catalog_runtime_insights_include_new_provider_blocks() -> None:
    service = GeospatialCatalogService(
        openaq_service=_OpenAQStub(),  # type: ignore[arg-type]
        pvgis_service=_PVGISStub(),  # type: ignore[arg-type]
        openmeteo_service=_OpenMeteoStub(),  # type: ignore[arg-type]
        overpass_service=_OverpassStub(),  # type: ignore[arg-type]
        rainviewer_service=_RainViewerStub(),  # type: ignore[arg-type]
    )

    insights = asyncio.run(
        service.fetch_insights(
            latitude=45.0,
            longitude=9.0,
            overlay_ids=[
                "openmeteo_weather_forecast",
                "openmeteo_air_quality_forecast",
                "overpass_poi_amenities",
                "rainviewer_precipitation_radar",
            ],
            radius_m=2500.0,
        )
    )
    runtime = asyncio.run(
        service.fetch_overlay_runtime(
            latitude=45.0,
            longitude=9.0,
            overlay_ids=[
                "openmeteo_weather_forecast",
                "openmeteo_air_quality_forecast",
                "overpass_poi_amenities",
                "rainviewer_precipitation_radar",
            ],
            radius_m=2500.0,
        )
    )

    assert "weather_forecast" in insights
    assert "air_quality_forecast" in insights
    assert "poi_amenities" in insights
    assert "rain_radar" in insights
    assert runtime["openmeteo_weather_forecast"]["availability"] == "available"
    assert runtime["rainviewer_precipitation_radar"]["availability"] == "available"
