from __future__ import annotations

from AEGIS.server.services.geospatial.catalog import GeospatialCatalogService
from AEGIS.server.services.geospatial.runtime_registry import RuntimeRegistry


class _CredentialRepo:
    def __init__(self, present: bool) -> None:
        self.present = present

    def get_active(self, *, provider: str, label: str):  # noqa: ANN201
        if self.present and provider in {"tomtom", "geoapify"} and label == "api_key":
            return object()
        return None


def _service_with_credentials(present: bool) -> GeospatialCatalogService:
    return GeospatialCatalogService(
        runtime_registry=RuntimeRegistry(credentials_repo=_CredentialRepo(present)),  # type: ignore[arg-type]
    )


def test_catalog_contains_grouped_capability_sections() -> None:
    catalog = _service_with_credentials(False).list_catalog()

    assert "providers" in catalog
    assert "basemaps" in catalog
    assert "overlays" in catalog
    assert "tools" in catalog
    assert any(item["id"] == "osm_default" for item in catalog["basemaps"])
    assert any(item["id"] == "openaq_air_quality" for item in catalog["overlays"])
    assert any(item["id"] == "get_weather_forecast" for item in catalog["tools"])


def test_catalog_marks_key_required_capabilities_unavailable_without_credentials(monkeypatch) -> None:
    monkeypatch.delenv("TOMTOM_API_KEY", raising=False)
    monkeypatch.delenv("GEOAPIFY_API_KEY", raising=False)

    catalog = _service_with_credentials(False).list_catalog()
    lookup = {item["id"]: item for item in catalog["capabilities"]}
    providers = {item["id"]: item for item in catalog["providers"]}

    assert lookup["tomtom_traffic_flow"]["requires_credentials"] is True
    assert lookup["tomtom_traffic_flow"]["is_available"] is False
    assert lookup["geoapify_osm"]["is_available"] is False
    assert providers["tomtom"]["is_available"] is False


def test_catalog_marks_key_required_capabilities_available_with_saved_credentials(monkeypatch) -> None:
    monkeypatch.delenv("TOMTOM_API_KEY", raising=False)
    monkeypatch.delenv("GEOAPIFY_API_KEY", raising=False)

    catalog = _service_with_credentials(True).list_catalog()
    lookup = {item["id"]: item for item in catalog["capabilities"]}
    providers = {item["id"]: item for item in catalog["providers"]}

    assert lookup["tomtom_traffic_flow"]["is_available"] is True
    assert lookup["geoapify_osm"]["is_available"] is True
    assert providers["tomtom"]["is_available"] is True
