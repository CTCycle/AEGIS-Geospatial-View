from __future__ import annotations

from server.domain.catalog import GeospatialLayerReferenceEntry
from server.services.geospatial.layers import LayerProviderService


def test_geospatial_layer_catalog_comes_from_reference_entries() -> None:
    service = LayerProviderService(
        layer_catalog=(
            GeospatialLayerReferenceEntry(
                layer_id="MODIS_Combined_Thermal_Anomalies_Fire",
                display_name="Active Fires (MODIS, Daily)",
                group="gibs_nrt",
                provider="gibs",
                aliases=("fire", "fires"),
                keywords=("fire", "fires"),
            ),
        )
    )

    entry = service.resolve("fires")

    assert entry.name == "MODIS_Combined_Thermal_Anomalies_Fire"
    assert entry.label == "Active Fires (MODIS, Daily)"
    assert entry.provider_name == "MODIS_Combined_Thermal_Anomalies_All"
