from __future__ import annotations

from server.services.geospatial.capability_registry import CapabilityRegistry

###############################################################################
def test_capability_registry_loads_tools() -> None:
    registry = CapabilityRegistry()
    snapshot = registry.load_capabilities()
    assert snapshot.tools
    assert registry.get_capability("get_weather_forecast") is not None

###############################################################################
def test_execution_contract_inference_covers_legacy_point_analysis_capability() -> None:
    contract = CapabilityRegistry().execution_contract(
        "openmeteo_pressure_humidity_wind"
    )

    assert contract["supported_scope_kinds"] == ["point", "bbox"]
    assert contract["temporal_modes"] == ["current", "forecast"]
    assert contract["render_support"] == "metadata_only"
    assert contract["output_geometry_type"] == "Point"
