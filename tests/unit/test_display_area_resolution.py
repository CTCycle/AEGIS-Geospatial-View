from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from AEGIS.server.api.search import MapRenderingService
from AEGIS.server.domain.geographics import LocationSearchRequest
from AEGIS.server.services.search.orchestrator import LocationSearchOrchestrator


class _ToolkitStub:
    def harmonize_bbox_crs(self, bbox, *, source_crs, target_crs):  # noqa: ANN001
        return bbox

    def normalize_layers(self, layers):  # noqa: ANN001
        return list(layers or [])

    def extract_coordinate_pair(self, payload, data):  # noqa: ANN001
        lat = data.get("latitude")
        lon = data.get("longitude")
        if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
            return (float(lon), float(lat))
        return None


class _MapServiceStub:
    def compute_bbox_from_center(self, lon: float, lat: float, size: float):  # noqa: ANN001
        return [lon - 0.1, lat - 0.1, lon + 0.1, lat + 0.1]


class _SanitizationStub:
    def sanitize_location_inputs(self, address: str, city: str | None, country: str | None) -> dict[str, str | None]:
        return {"address": address, "city": city, "country": country, "country_code": "it"}


class _NominatimCitySuccessStub:
    async def extract_coordinates(self, address, city, country_name, country_code, limit=1):  # noqa: ANN001
        if city == "Rome":
            return {"lat": 41.9, "lon": 12.5, "bbox": [12.4, 41.8, 12.6, 42.0], "confidence": 0.9}
        return None

    async def extract_bbox_from_coordinates(self, latitude, longitude):  # noqa: ANN001
        return [longitude - 0.1, latitude - 0.1, longitude + 0.1, latitude + 0.1]


class _NominatimFailStub:
    async def extract_coordinates(self, address, city, country_name, country_code, limit=1):  # noqa: ANN001
        return None

    async def extract_bbox_from_coordinates(self, latitude, longitude):  # noqa: ANN001
        return None


class _RendererStub:
    async def build_satellite_payload(self, payload, search_payload):  # noqa: ANN001
        return {"bbox": search_payload.get("bbox") or [12.4, 41.8, 12.6, 42.0]}


class _CatalogStub:
    def resolve_overlays(self, overlay_ids):  # noqa: ANN001
        return []

    def resolve_basemap(self, basemap_id):  # noqa: ANN001
        return {"id": basemap_id or "osm_default"}

    async def fetch_insights(self, latitude, longitude, overlay_ids, radius_m):  # noqa: ANN001
        return {}

    async def fetch_overlay_runtime(self, latitude, longitude, overlay_ids, radius_m):  # noqa: ANN001
        _ = latitude, longitude, radius_m
        return {str(overlay_id): {"availability": "available"} for overlay_id in overlay_ids}

    def resolve_compliance_warnings(self, basemap, overlays):  # noqa: ANN001
        return []


class _ElevationStub:
    async def get_elevation(self, lat, lon):  # noqa: ANN001
        return None


def _build_renderer_service() -> MapRenderingService:
    service = MapRenderingService.__new__(MapRenderingService)
    service.toolkit = _ToolkitStub()
    service.map_service = _MapServiceStub()
    return service


def _build_orchestrator(nominatim_service) -> LocationSearchOrchestrator:  # noqa: ANN001
    return LocationSearchOrchestrator(
        sanitization_service=_SanitizationStub(),
        nominatim_service=nominatim_service,
        catalog_service=_CatalogStub(),
        elevation_service=_ElevationStub(),
        renderer=_RendererStub(),
        toolkit=_ToolkitStub(),
    )


def test_derive_map_bbox_prefers_explicit_bbox() -> None:
    service = _build_renderer_service()
    payload = SimpleNamespace(
        bbox=[1.0, 2.0, 3.0, 4.0],
        image_crs="EPSG:4326",
        aoi=None,
        map_size_m=2500.0,
    )
    result = service._derive_map_bbox(  # type: ignore[attr-defined]
        bbox_candidate=[0.0, 0.0, 1.0, 1.0],
        bbox_source_crs="EPSG:4326",
        coordinates=(12.5, 41.9),
        payload=payload,
    )
    assert result == [1.0, 2.0, 3.0, 4.0]


def test_city_only_location_resolves_without_generic_extent_error() -> None:
    orchestrator = _build_orchestrator(_NominatimCitySuccessStub())
    payload = LocationSearchRequest(city="Rome")
    result = asyncio.run(orchestrator.execute(payload))
    assert result["payload"].get("latitude") is not None
    assert result["payload"].get("longitude") is not None


def test_unresolved_location_fails_with_actionable_error() -> None:
    orchestrator = _build_orchestrator(_NominatimFailStub())
    payload = LocationSearchRequest(city="Unknown Place", country="Nowhere Land")
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(orchestrator.execute(payload))
    assert exc_info.value.status_code == 400
    assert "Unable to resolve a usable location" in str(exc_info.value.detail)
    assert "Unable to resolve map extent for the requested imagery." not in str(exc_info.value.detail)
