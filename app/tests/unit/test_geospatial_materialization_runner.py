from __future__ import annotations

import json
from pathlib import Path

from server.services.geospatial.materialization_runner import materialize_datasets


def _write_manifest(path: Path, capability_id: str, source_file: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "id": capability_id,
                "capabilityKind": "dataset-ingestion",
                "download": {
                    "sourceUrl": str(source_file),
                    "license": "test",
                    "updateFrequency": "static",
                    "expectedFormat": "geojson",
                    "checksumUrl": None,
                    "compression": "none",
                },
                "storage": {
                    "rawPath": f"data/raw/{capability_id}/",
                    "normalizedPath": f"data/normalized/{capability_id}/",
                    "tilePath": f"data/tiles/{capability_id}/",
                },
                "normalization": {
                    "targetCrs": "EPSG:4326",
                    "geometryType": "Point",
                    "idField": "id",
                    "fieldMap": {},
                },
                "indexing": {
                    "spatialIndex": True,
                    "textIndex": True,
                    "vectorTile": False,
                },
                "validation": {"minFeatureCount": 1},
            }
        ),
        encoding="utf-8",
    )


def test_materialize_datasets_filters_by_capability_id(tmp_path: Path) -> None:
    manifest_root = tmp_path / "manifests"
    manifest_root.mkdir(parents=True)

    source_a = tmp_path / "a.geojson"
    source_a.write_text(
        '{"type":"FeatureCollection","features":[{"type":"Feature","id":"a","properties":{"name":"A"},"geometry":{"type":"Point","coordinates":[12.0,41.0]}}]}',
        encoding="utf-8",
    )
    source_b = tmp_path / "b.geojson"
    source_b.write_text(
        '{"type":"FeatureCollection","features":[{"type":"Feature","id":"b","properties":{"name":"B"},"geometry":{"type":"Point","coordinates":[13.0,42.0]}}]}',
        encoding="utf-8",
    )

    _write_manifest(manifest_root / "dataset_a.json", "dataset_a", source_a)
    _write_manifest(manifest_root / "dataset_b.json", "dataset_b", source_b)

    results = materialize_datasets(
        workspace_root=tmp_path,
        manifest_root=manifest_root,
        include_ids={"dataset_b"},
    )

    assert len(results) == 1
    assert results[0]["capabilityId"] == "dataset_b"
    assert results[0]["featureCount"] == 1
