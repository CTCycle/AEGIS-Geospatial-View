from __future__ import annotations

from server.services.geospatial.ingestion import (
    IngestionManifestError,
    build_ingestion_plan,
    execute_ingestion_plan,
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


def test_execute_ingestion_plan_normalizes_csv_and_writes_indexes(tmp_path) -> None:
    source = tmp_path / "airports.csv"
    source.write_text(
        "id,name,latitude_deg,longitude_deg,type\n"
        "1,Test Airport,45.0,7.0,small_airport\n"
        "2,Bad Airport,not-a-number,7.1,closed\n",
        encoding="utf-8",
    )
    manifest = _manifest()
    manifest["download"]["sourceUrl"] = str(source)
    manifest["download"]["expectedFormat"] = "csv"
    manifest["download"]["compression"] = "none"
    manifest["normalization"]["idField"] = "id"
    manifest["validation"] = {"minFeatureCount": 1}
    plan = build_ingestion_plan(manifest)

    result = execute_ingestion_plan(plan, workspace_root=tmp_path)

    assert result.feature_count == 1
    assert result.normalized_file is not None
    assert result.spatial_index_file is not None
    assert result.text_index_file is not None
    assert result.tile_manifest_file is not None


def test_execute_ingestion_plan_rejects_checksum_mismatch(tmp_path) -> None:
    source = tmp_path / "source.geojson"
    source.write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")
    manifest = _manifest()
    manifest["download"]["sourceUrl"] = str(source)
    manifest["download"]["expectedFormat"] = "geojson"
    manifest["download"]["checksumSha256"] = "0" * 64
    manifest["validation"] = {"minFeatureCount": 0}
    plan = build_ingestion_plan(manifest)

    try:
        execute_ingestion_plan(plan, workspace_root=tmp_path)
    except RuntimeError as exc:
        assert "Checksum mismatch" in str(exc)
    else:
        raise AssertionError("Checksum mismatch did not fail ingestion.")
