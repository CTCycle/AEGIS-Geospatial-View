from __future__ import annotations

import hashlib

from server.services.geospatial.ingestion import (
    build_ingestion_plan,
    execute_ingestion_plan,
    validate_ingestion_manifest,
)


###############################################################################
def _manifest(source: str) -> dict:
    return {
        "id": "validation_sample",
        "capabilityKind": "dataset-ingestion",
        "download": {
            "sourceUrl": source,
            "license": "test",
            "updateFrequency": "static",
            "expectedFormat": "geojson",
            "compression": "none",
        },
        "storage": {
            "rawPath": "raw/sample",
            "normalizedPath": "normalized/sample",
            "tilePath": "tiles/sample",
        },
        "normalization": {
            "targetCrs": "EPSG:4326",
            "geometryType": "Point",
            "idField": "id",
            "fieldMap": {},
        },
        "indexing": {"spatialIndex": True, "textIndex": True, "vectorTile": True},
        "validation": {"minFeatureCount": 0},
    }


###############################################################################
def test_ingestion_validation_reports_missing_download_fields(tmp_path) -> None:
    manifest = _manifest(str(tmp_path / "missing.geojson"))
    del manifest["download"]["sourceUrl"]

    errors = validate_ingestion_manifest(manifest)

    assert errors
    assert "sourceUrl" in errors[0]


###############################################################################
def test_ingestion_validation_accepts_checksum_url(tmp_path) -> None:
    source = tmp_path / "source.geojson"
    source.write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")
    checksum = hashlib.sha256(source.read_bytes()).hexdigest()
    checksum_file = tmp_path / "source.sha256"
    checksum_file.write_text(f"{checksum}  source.geojson\n", encoding="utf-8")
    manifest = _manifest(str(source))
    manifest["download"]["checksumUrl"] = str(checksum_file)

    result = execute_ingestion_plan(build_ingestion_plan(manifest), workspace_root=tmp_path)

    assert result.feature_count == 0
    assert result.metadata_file.endswith("source_metadata.json")
