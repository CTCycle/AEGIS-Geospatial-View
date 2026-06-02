from __future__ import annotations

from pathlib import Path

from server.services.geospatial.manifest_loader import GeospatialManifestLoader


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


def test_priority_provider_manifests_include_temporal_metadata() -> None:
    payload = GeospatialManifestLoader().load_all()
    providers = {item["id"]: item for item in payload["providers"]}
    for provider_id in ("inspire", "data_europa", "arcgis", "geoss", "google_maps"):
        metadata = providers[provider_id]["metadata"]
        assert metadata["dataset_time_reference"]
        assert metadata["source_freshness"]
        assert metadata["query_mode"]


def test_manifest_loader_accepts_path_root_argument() -> None:
    root_path = Path("app/resources/manifests")

    payload = GeospatialManifestLoader(root_path=root_path).load_all()

    assert any(item["id"] == "osm_default" for item in payload["basemaps"])
