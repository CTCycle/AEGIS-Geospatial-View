from __future__ import annotations

from server.services.geospatial.endpoint_validation import EndpointValidationService
from server.services.geospatial.manifest_loader import GeospatialManifestLoader
from server.services.geospatial.runtime_registry import RuntimeRegistry


class _NoCredentials:
    def get_active(self, *, provider: str, label: str):  # noqa: ANN201
        return None


REQUIRED_TRAIT_FIELDS = {
    "official_docs_url",
    "source_protocol",
    "data_format",
    "geometry_type",
    "endpoint_health",
    "auth_mode",
    "rate_limit_notes",
}


def test_all_manifest_entries_expose_source_traits() -> None:
    payload = GeospatialManifestLoader().load_all()
    missing: list[str] = []
    for collection_name in ("providers", "basemaps", "overlays", "tools"):
        for item in payload[collection_name]:
            metadata = dict(item.get("metadata") or {})
            for field in REQUIRED_TRAIT_FIELDS:
                if not metadata.get(field):
                    missing.append(f"{collection_name}:{item['id']}:metadata.{field}")
    assert not missing

def test_credentialed_capabilities_are_not_healthy_without_credentials(monkeypatch) -> None:
    monkeypatch.delenv("OPENAQ_API_KEY", raising=False)
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    runtime = RuntimeRegistry(credentials_repo=_NoCredentials())  # type: ignore[arg-type]
    runtime.build_snapshot()

    assert runtime.provider_health("openaq_air_quality") == "missing_credentials"
    assert runtime.provider_health("fred_regional_market_indicators") == "missing_credentials"


def test_endpoint_validation_builds_sampled_urls_without_network_calls() -> None:
    payload = GeospatialManifestLoader().load_all()
    overlays = {item["id"]: item for item in payload["overlays"]}
    service = EndpointValidationService()

    census_url = service.build_validation_url(overlays["census_tigerweb_hydrography"])
    assert census_url is not None
    assert "{bbox}" not in census_url
    assert "f=geojson" in census_url

    esa_url = service.build_validation_url(overlays["esa_worldcover"])
    assert esa_url is not None
    assert "GetCapabilities" in esa_url
