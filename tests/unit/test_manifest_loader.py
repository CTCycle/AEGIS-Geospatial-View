from __future__ import annotations

from AEGIS.server.services.geospatial.manifest_loader import GeospatialManifestLoader


def test_manifest_loader_reads_core_collections() -> None:
    loader = GeospatialManifestLoader()
    payload = loader.load_all()
    assert "providers" in payload
    assert "basemaps" in payload
    assert "overlays" in payload
    assert any(item["id"] == "osm_default" for item in payload["basemaps"])
    assert any(item["id"] == "openaq_air_quality" for item in payload["overlays"])
    basemap = next(item for item in payload["basemaps"] if item["id"] == "osm_default")
    assert basemap.get("source_filename")
    assert basemap.get("source_path")
