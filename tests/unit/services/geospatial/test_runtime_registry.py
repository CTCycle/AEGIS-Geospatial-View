from __future__ import annotations

from AEGIS.server.services.geospatial.capability_registry import CapabilityRegistry
from AEGIS.server.services.geospatial.runtime_registry import RuntimeRegistry


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
