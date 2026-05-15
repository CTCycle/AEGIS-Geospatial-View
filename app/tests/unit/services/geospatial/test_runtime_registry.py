from __future__ import annotations

from server.services.geospatial.capability_registry import CapabilityRegistry
from server.services.geospatial.runtime_registry import RuntimeRegistry


class _CredentialRepo:
    def __init__(self, present: bool) -> None:
        self.present = present

    def get_active(self, *, provider: str, label: str):  # noqa: ANN201
        if self.present and provider in {"tomtom", "geoapify"} and label == "api_key":
            return object()
        return None


def test_runtime_registry_reads_profiles() -> None:
    registry = RuntimeRegistry()
    snapshot = registry.build_snapshot()
    assert "osm_default" in snapshot.profiles
    assert registry.is_enabled("osm_default")


def test_runtime_profiles_cover_all_capabilities() -> None:
    capability_registry = CapabilityRegistry()
    capabilities = capability_registry.load_capabilities()
    all_capability_ids = {
        *(str(item.get("id")) for item in capabilities.basemaps),
        *(str(item.get("id")) for item in capabilities.overlays),
        *(str(item.get("id")) for item in capabilities.tools),
    }
    runtime_profiles = RuntimeRegistry().build_snapshot().profiles
    missing = sorted(capability_id for capability_id in all_capability_ids if capability_id not in runtime_profiles)
    assert not missing


def test_key_required_providers_are_unavailable_without_saved_credentials(monkeypatch) -> None:
    monkeypatch.delenv("TOMTOM_API_KEY", raising=False)
    monkeypatch.delenv("GEOAPIFY_API_KEY", raising=False)
    registry = RuntimeRegistry(credentials_repo=_CredentialRepo(False))  # type: ignore[arg-type]
    registry.build_snapshot()

    assert not registry.credentials_present("tomtom_traffic_flow")
    assert registry.provider_health("tomtom_traffic_flow") == "missing_credentials"
    assert not registry.credentials_present("geoapify_osm")


def test_key_required_providers_use_saved_credentials(monkeypatch) -> None:
    monkeypatch.delenv("TOMTOM_API_KEY", raising=False)
    monkeypatch.delenv("GEOAPIFY_API_KEY", raising=False)
    registry = RuntimeRegistry(credentials_repo=_CredentialRepo(True))  # type: ignore[arg-type]
    registry.build_snapshot()

    assert registry.credentials_present("tomtom_traffic_flow")
    assert registry.provider_health("tomtom_traffic_flow") == "healthy"
    assert registry.credentials_present("geoapify_osm")
