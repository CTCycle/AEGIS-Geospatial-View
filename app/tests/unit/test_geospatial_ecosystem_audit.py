from __future__ import annotations

from server.services.geospatial.ecosystem_audit import build_inventory


def test_ecosystem_inventory_covers_catalog_runtime_and_native_tools() -> None:
    report = build_inventory(
        {
            "results": [
                {"provider_id": "openmeteo", "status": "passed"},
                {"provider_id": "geoapify", "status": "skipped"},
            ]
        }
    )

    assert report["counts"] == {
        "manifests": 86,
        "providers": 40,
        "direct_tools": 4,
        "llm_native_tools": 5,
        "runtime_profiles": 68,
    }
    providers = {item["id"]: item for item in report["providers"]}
    assert providers["openmeteo"]["operational_status"] == "active"
    assert providers["geoapify"]["operational_status"] == "partial_missing_credentials"
    assert providers["openfreemap"]["operational_status"] == "active_rendering_only"
    assert providers["arcgis"]["internal_components"]["adapter"].endswith("arcgis_rest.py")

    tool_ids = {item["id"] for item in report["tools"]}
    assert "render_geospatial_provider_layer" in tool_ids
    assert "execute_geospatial_capability" in tool_ids
    assert report["replacements"][1]["new"] == ["mobility_database_feeds"]
