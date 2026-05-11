from __future__ import annotations

from pathlib import Path


def test_client_geospatial_e2e_scenario_specs_exist() -> None:
    root = Path("app/client/e2e")

    layers = root / "geospatial-layers.spec.ts"
    webcams = root / "geospatial-webcams.spec.ts"

    assert layers.is_file()
    assert webcams.is_file()
    assert "rainviewer_precipitation_radar" in layers.read_text(encoding="utf-8")
    assert "windy_webcams_missing_key" in webcams.read_text(encoding="utf-8")
