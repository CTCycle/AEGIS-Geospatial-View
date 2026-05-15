from __future__ import annotations

import json
from pathlib import Path

from server.services.geospatial.ingestion import build_ingestion_plan, execute_ingestion_plan


def test_dataset_ingestion_writes_health_record(tmp_path) -> None:
    source = tmp_path / "source.geojson"
    source.write_text(
        """
        {
          "type": "FeatureCollection",
          "features": [
            {
              "type": "Feature",
              "id": "a",
              "properties": {"name": "A"},
              "geometry": {"type": "Point", "coordinates": [12.5, 41.9]}
            }
          ]
        }
        """,
        encoding="utf-8",
    )
    manifest = {
        "id": "health_sample",
        "capabilityKind": "dataset-ingestion",
        "download": {
            "sourceUrl": str(source),
            "license": "test",
            "updateFrequency": "static",
            "expectedFormat": "geojson",
            "compression": "none",
        },
        "storage": {
            "rawPath": "raw/health",
            "normalizedPath": "normalized/health",
            "tilePath": "tiles/health",
        },
        "normalization": {
            "targetCrs": "EPSG:4326",
            "geometryType": "Point",
            "idField": "id",
            "fieldMap": {},
        },
        "indexing": {"spatialIndex": True, "textIndex": True, "vectorTile": True},
        "validation": {"minFeatureCount": 1},
    }

    result = execute_ingestion_plan(build_ingestion_plan(manifest), workspace_root=tmp_path)
    health = json.loads(Path(result.health_file).read_text(encoding="utf-8"))

    assert health["capabilityId"] == "health_sample"
    assert health["status"] == "functional"
    assert health["featureCount"] == 1
