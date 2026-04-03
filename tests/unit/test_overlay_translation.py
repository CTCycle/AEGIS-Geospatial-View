from __future__ import annotations

from AEGIS.server.services.geospatial.manifest_loader import GeospatialManifestLoader
from AEGIS.server.services.geospatial.overlay_translation import (
    translate_overlay_ids_to_filters,
)


def test_overlay_translation_handles_gibs_legacy_ids() -> None:
    overlays = GeospatialManifestLoader().load_all()["overlays"]
    translated = translate_overlay_ids_to_filters(
        ["GIBS_MODIS_Combined_Thermal_Anomalies_Fire", "openaq_air_quality"],
        overlays,
    )
    assert "MODIS_Combined_Thermal_Anomalies_Fire" in translated
    assert "openaq_air_quality" in translated
