from __future__ import annotations

from server.services.geospatial.capability_registry import (
    CapabilityRegistry,
    normalized_execution_contract,
)

###############################################################################
def test_capability_registry_loads_tools() -> None:
    registry = CapabilityRegistry()
    snapshot = registry.load_capabilities()
    assert snapshot.tools
    assert registry.get_capability("get_weather_forecast") is not None

###############################################################################
def test_execution_contract_is_read_from_the_manifest() -> None:
    contract = CapabilityRegistry().execution_contract(
        "openmeteo_weather_forecast"
    )

    assert contract["supported_operations"] == ["show", "inspect", "forecast"]
    assert contract["supported_scope_kinds"] == ["point", "bbox"]
    assert contract["render_support"] == "vector"
    assert contract["output_geometry_type"] == "Point"


def test_execution_contract_is_not_inferred_for_an_incomplete_manifest() -> None:
    contract = normalized_execution_contract(
        {
            "id": "incomplete",
            "type": "time-series-insight",
            "capabilityKind": "analysis-tool",
            "name": "Weather forecast",
            "metadata": {"geometry_type": "point", "queryable": True},
        }
    )

    assert contract["supported_operations"] == []
    assert contract["supported_scope_kinds"] == []
    assert contract["render_support"] == "none"
