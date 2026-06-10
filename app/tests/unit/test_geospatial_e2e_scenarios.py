from __future__ import annotations

from pathlib import Path


###############################################################################
def test_client_geospatial_e2e_scenario_specs_exist() -> None:
    root = Path("app/client/e2e")

    layers = root / "geospatial-layers.spec.ts"
    webcams = root / "geospatial-webcams.spec.ts"

    assert layers.is_file()
    assert webcams.is_file()
    assert "rainviewer_precipitation_radar" in layers.read_text(encoding="utf-8")
    assert "windy_webcams_missing_key" in webcams.read_text(encoding="utf-8")
    assert "workflow_show_rome_italy" in layers.read_text(encoding="utf-8")
    assert "workflow_show_rome_with_traffic" in layers.read_text(encoding="utf-8")
    assert "workflow_show_zurich_with_precipitation_radar" in layers.read_text(
        encoding="utf-8"
    )
    assert "workflow_show_paris_with_air_quality" in layers.read_text(encoding="utf-8")
    assert "workflow_show_previous_location_with_traffic" in layers.read_text(
        encoding="utf-8"
    )
    assert "workflow_show_traffic_and_rain_coordinates" in layers.read_text(
        encoding="utf-8"
    )
    assert "workflow_missing_api_keys" in layers.read_text(encoding="utf-8")
    assert "workflow_broken_provider_response" in layers.read_text(encoding="utf-8")
    assert "workflow_show_webcams_times_square" in webcams.read_text(encoding="utf-8")
