from __future__ import annotations

from server.domain.catalog import GeospatialLayerReferenceEntry
from server.services.geospatial.layers import LayerProviderService

###############################################################################
def test_layer_provider_maps_active_fires_to_supported_provider_layer() -> None:
    service = LayerProviderService(
        layer_catalog=(
            GeospatialLayerReferenceEntry(
                layer_id="MODIS_Combined_Thermal_Anomalies_Fire",
                display_name="Active Fires (MODIS, Daily)",
                group="gibs_nrt",
                provider="gibs",
                aliases=("active fires", "fire", "fires"),
                keywords=("active fires", "fire", "fires"),
            ),
        )
    )

    entry = service.resolve("MODIS_Combined_Thermal_Anomalies_Fire")

    assert entry.name == "MODIS_Combined_Thermal_Anomalies_Fire"
    assert entry.provider_name == "MODIS_Combined_Thermal_Anomalies_All"

