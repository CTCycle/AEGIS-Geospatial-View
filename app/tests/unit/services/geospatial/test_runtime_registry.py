from __future__ import annotations

from server.services.geospatial.capability_registry import CapabilityRegistry
from server.services.geospatial.manifest_loader import GeospatialManifestLoader
from server.services.geospatial.runtime_registry import RuntimeRegistry

###############################################################################
class _CredentialRepo:

    # -------------------------------------------------------------------------
    def __init__(self, present: bool) -> None:
        self.present = present

    # -------------------------------------------------------------------------
    def get_active(self, *, provider: str, label: str):  # noqa: ANN201
        if (
            self.present
            and provider in {"tomtom", "openchargemap"}
            and label == "api_key"
        ):
            return object()
        return None

###############################################################################
def test_runtime_registry_reads_profiles() -> None:
    registry = RuntimeRegistry(
        manifest_loader=GeospatialManifestLoader(),
        credentials_repo=_CredentialRepo(False),
    )
    snapshot = registry.build_snapshot()
    assert "osm_default" in snapshot.profiles
    assert registry.is_enabled("osm_default")

###############################################################################
def test_runtime_profiles_cover_all_capabilities() -> None:
    capability_registry = CapabilityRegistry()
    capabilities = capability_registry.load_capabilities()
    all_capability_ids = {
        *(str(item.get("id")) for item in capabilities.basemaps),
        *(str(item.get("id")) for item in capabilities.overlays),
        *(str(item.get("id")) for item in capabilities.tools),
    }
    runtime_profiles = (
        RuntimeRegistry(
            manifest_loader=GeospatialManifestLoader(),
            credentials_repo=_CredentialRepo(False),
        )
        .build_snapshot()
        .profiles
    )
    missing = sorted(
        capability_id
        for capability_id in all_capability_ids
        if capability_id not in runtime_profiles
    )
    assert not missing

###############################################################################
def test_key_required_providers_are_unavailable_without_saved_credentials(
    monkeypatch,
) -> None:
    monkeypatch.delenv("TOMTOM_API_KEY", raising=False)
    registry = RuntimeRegistry(
        manifest_loader=GeospatialManifestLoader(),
        credentials_repo=_CredentialRepo(False),
    )  # type: ignore[arg-type]
    registry.build_snapshot()

    assert not registry.credentials_present("tomtom_traffic_flow")
    assert registry.provider_health("tomtom_traffic_flow") == "missing_credentials"

###############################################################################
def test_key_required_providers_use_saved_credentials(monkeypatch) -> None:
    monkeypatch.delenv("TOMTOM_API_KEY", raising=False)
    registry = RuntimeRegistry(
        manifest_loader=GeospatialManifestLoader(),
        credentials_repo=_CredentialRepo(True),
    )  # type: ignore[arg-type]
    registry.build_snapshot()

    assert registry.credentials_present("tomtom_traffic_flow")
    assert registry.provider_health("tomtom_traffic_flow") == "healthy"

###############################################################################
def test_openchargemap_requires_saved_key_or_local_snapshot(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("AEGIS_OCM_SNAPSHOT_PATH", raising=False)
    unavailable = RuntimeRegistry(
        manifest_loader=GeospatialManifestLoader(),
        credentials_repo=_CredentialRepo(False),
    )  # type: ignore[arg-type]

    assert not unavailable.access_available("openchargemap_ev_charging")
    assert unavailable.provider_health("openchargemap_ev_charging") == "missing_access"
    assert "Open Charge Map" in (
        unavailable.access_reason("openchargemap_ev_charging") or ""
    )

    snapshot = tmp_path / "openchargemap.json"
    snapshot.write_text("[]", encoding="utf-8")
    monkeypatch.setenv("AEGIS_OCM_SNAPSHOT_PATH", str(snapshot))
    local = RuntimeRegistry(
        manifest_loader=GeospatialManifestLoader(),
        credentials_repo=_CredentialRepo(False),
    )  # type: ignore[arg-type]

    assert local.access_available("openchargemap_ev_charging")
    assert local.provider_health("openchargemap_ev_charging") == "healthy"

###############################################################################
def test_openchargemap_is_available_with_saved_access_credential(monkeypatch) -> None:
    monkeypatch.delenv("AEGIS_OCM_SNAPSHOT_PATH", raising=False)
    registry = RuntimeRegistry(
        manifest_loader=GeospatialManifestLoader(),
        credentials_repo=_CredentialRepo(True),
    )  # type: ignore[arg-type]

    assert registry.access_available("openchargemap_ev_charging")
    assert registry.provider_health("openchargemap_ev_charging") == "healthy"

###############################################################################
def test_restricted_capability_is_disabled_without_explicit_opt_in(monkeypatch) -> None:
    monkeypatch.delenv("AEGIS_ALLOW_RESTRICTED_SOURCES", raising=False)
    registry = RuntimeRegistry(
        manifest_loader=GeospatialManifestLoader(),
        credentials_repo=_CredentialRepo(False),
    )

    assert not registry.is_enabled("openmeteo_elevation")
    assert registry.provider_health("openmeteo_elevation") == "disabled"

###############################################################################
def test_restricted_capability_requires_explicit_opt_in(monkeypatch) -> None:
    monkeypatch.setenv("AEGIS_ALLOW_RESTRICTED_SOURCES", "true")
    registry = RuntimeRegistry(
        manifest_loader=GeospatialManifestLoader(),
        credentials_repo=_CredentialRepo(False),
    )

    assert registry.is_enabled("openmeteo_elevation")
    assert registry.provider_health("openmeteo_elevation") == "healthy"
