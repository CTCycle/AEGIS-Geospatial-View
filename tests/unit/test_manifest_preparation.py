from __future__ import annotations

from AEGIS.server.services.vector.manifest_preparation import ManifestPreparationService


def test_prepare_entry_creates_single_chunk_for_manifest() -> None:
    service = ManifestPreparationService()
    entry = {
        "id": "osm_default",
        "name": "OpenStreetMap",
        "provider": "fallback",
        "type": "tile",
        "description": "General city streets basemap.",
        "coverage": "global",
        "capabilities": ["tile"],
        "source_path": "/tmp/manifests/basemaps/osm_default.json",
        "source_filename": "osm_default.json",
        "metadata": {
            "keywords": ["streets", "roads"],
            "human_summary": "Best baseline for routing and city context.",
            "primary_use_cases": ["routing", "city orientation"],
            "search_examples": ["show roads in Rome"],
            "disambiguation_notes": ["Prefer satellite for terrain texture."],
            "location_dependency": "Requires map location to focus area.",
            "integration_requirements": ["No key required"],
        },
    }
    chunk = service.prepare_entry(entry=entry, kind="basemaps")
    assert chunk.id == "basemaps:osm_default"
    assert "Human summary:" in chunk.text
    assert "Primary use cases:" in chunk.text
    assert chunk.metadata["document_kind"] == "basemap"
    assert chunk.metadata["source_filename"] == "osm_default.json"
    assert chunk.metadata["source_path"] == "/tmp/manifests/basemaps/osm_default.json"
