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


def test_catalog_contains_expected_core_sections() -> None:
    service = GeospatialCatalogService(
        openaq_service=_OpenAQStub(),  # type: ignore[arg-type]
        pvgis_service=_PVGISStub(),  # type: ignore[arg-type]
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
    )

    resolved = service.resolve_overlays(["openaq_air_quality", "unknown_overlay"])

    assert len(resolved) == 1
    assert resolved[0]["id"] == "openaq_air_quality"


def test_insights_are_cached_for_same_aoi() -> None:
    service = GeospatialCatalogService(
        openaq_service=_OpenAQStub(),  # type: ignore[arg-type]
        pvgis_service=_PVGISStub(),  # type: ignore[arg-type]
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
