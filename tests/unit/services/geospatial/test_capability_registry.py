from __future__ import annotations

from AEGIS.server.services.geospatial.capability_registry import CapabilityRegistry


def test_capability_registry_loads_tools() -> None:
    registry = CapabilityRegistry()
    snapshot = registry.load_capabilities()
    assert snapshot.tools
    assert registry.get_capability("get_weather_forecast") is not None
