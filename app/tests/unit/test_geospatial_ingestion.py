from __future__ import annotations

from server.services.geospatial.ingestion import (
    IngestionManifestError,
    build_ingestion_plan,
    validate_ingestion_manifest,
)


def _manifest():
    return {
        "id": "natural_earth_admin",
        "capabilityKind": "dataset-ingestion",
        "download": {
            "sourceUrl": "https://example.test/ne.zip",
            "license": "public domain",
            "updateFrequency": "static",
            "expectedFormat": "shapefile",
            "checksumUrl": None,
            "compression": "zip",
        },
        "storage": {
            "rawPath": "data/geospatial/raw/natural_earth/admin/",
            "normalizedPath": "data/geospatial/normalized/natural_earth/admin/",
            "tilePath": "data/geospatial/tiles/natural_earth/admin/",
        },
        "normalization": {
            "targetCrs": "EPSG:4326",
            "geometryType": "Polygon",
            "idField": "ne_id",
            "fieldMap": {},
        },
        "indexing": {
            "spatialIndex": True,
            "textIndex": True,
            "vectorTile": True,
        },
    }


def test_build_ingestion_plan_from_manifest() -> None:
    plan = build_ingestion_plan(_manifest())

    assert plan.capability_id == "natural_earth_admin"
    assert plan.expected_format == "shapefile"
    assert plan.spatial_index is True


def test_validate_ingestion_manifest_reports_missing_fields() -> None:
    manifest = _manifest()
    del manifest["download"]["sourceUrl"]

    errors = validate_ingestion_manifest(manifest)

    assert errors
    assert "sourceUrl" in errors[0]


def test_build_ingestion_plan_rejects_non_ingestion_manifest() -> None:
    try:
        build_ingestion_plan({"id": "osm_default", "capabilityKind": "basemap"})
    except IngestionManifestError as exc:
        assert "dataset-ingestion" in str(exc)
    else:
        raise AssertionError("Non-ingestion manifest unexpectedly produced a plan.")
