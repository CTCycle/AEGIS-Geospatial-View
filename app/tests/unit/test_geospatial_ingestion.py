from __future__ import annotations

import hashlib
import json
from pathlib import Path

from server.services.geospatial.ingestion import (
    IngestionManifestError,
    build_ingestion_plan,
    execute_ingestion_plan,
    validate_ingestion_manifest,
)


###############################################################################
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


###############################################################################
def test_build_ingestion_plan_from_manifest() -> None:
    plan = build_ingestion_plan(_manifest())

    assert plan.capability_id == "natural_earth_admin"
    assert plan.expected_format == "shapefile"
    assert plan.spatial_index is True


###############################################################################
def test_validate_ingestion_manifest_reports_missing_fields() -> None:
    manifest = _manifest()
    del manifest["download"]["sourceUrl"]

    errors = validate_ingestion_manifest(manifest)

    assert errors
    assert "sourceUrl" in errors[0]


###############################################################################
def test_build_ingestion_plan_rejects_non_ingestion_manifest() -> None:
    try:
        build_ingestion_plan({"id": "osm_default", "capabilityKind": "basemap"})
    except IngestionManifestError as exc:
        assert "dataset-ingestion" in str(exc)
    else:
        raise AssertionError("Non-ingestion manifest unexpectedly produced a plan.")


###############################################################################
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


###############################################################################
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


###############################################################################
def test_execute_ingestion_plan_accepts_checksum_url(tmp_path) -> None:
    source = tmp_path / "source.geojson"
    source.write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")
    checksum = hashlib.sha256(source.read_bytes()).hexdigest()
    checksum_file = tmp_path / "source.sha256"
    checksum_file.write_text(f"{checksum}  source.geojson\n", encoding="utf-8")
    manifest = _manifest()
    manifest["download"]["sourceUrl"] = str(source)
    manifest["download"]["expectedFormat"] = "geojson"
    manifest["download"]["checksumUrl"] = str(checksum_file)
    manifest["validation"] = {"minFeatureCount": 0}
    plan = build_ingestion_plan(manifest)

    result = execute_ingestion_plan(plan, workspace_root=tmp_path)

    assert result.feature_count == 0
    assert '"checksumSource": "checksumUrl"' in Path(result.metadata_file).read_text(encoding="utf-8")


###############################################################################
def test_execute_ingestion_plan_drops_invalid_geojson_geometry(tmp_path) -> None:
    source = tmp_path / "source.geojson"
    source.write_text(
        """
        {
          "type": "FeatureCollection",
          "features": [
            {
              "type": "Feature",
              "id": "valid-line",
              "properties": {"name": "Valid line"},
              "geometry": {
                "type": "LineString",
                "coordinates": [[7.0, 45.0], [7.2, 45.2]]
              }
            },
            {
              "type": "Feature",
              "id": "bad-point",
              "properties": {"name": "Bad point"},
              "geometry": {"type": "Point", "coordinates": [220.0, 45.0]}
            }
          ]
        }
        """,
        encoding="utf-8",
    )
    manifest = _manifest()
    manifest["download"]["sourceUrl"] = str(source)
    manifest["download"]["expectedFormat"] = "geojson"
    manifest["download"]["compression"] = "none"
    manifest["validation"] = {"minFeatureCount": 1}
    plan = build_ingestion_plan(manifest)

    result = execute_ingestion_plan(plan, workspace_root=tmp_path)

    assert result.feature_count == 1
    assert "Dropped 1 GeoJSON feature" in result.warnings[0]
    assert result.spatial_index_file is not None
    assert '"bbox": [' in Path(result.spatial_index_file).read_text(encoding="utf-8")


###############################################################################
def test_execute_ingestion_plan_rejects_non_intersecting_bbox(tmp_path) -> None:
    source = tmp_path / "source.geojson"
    source.write_text(
        """
        {
          "type": "FeatureCollection",
          "features": [
            {
              "type": "Feature",
              "id": "outside",
              "properties": {"name": "Outside"},
              "geometry": {"type": "Point", "coordinates": [7.0, 45.0]}
            }
          ]
        }
        """,
        encoding="utf-8",
    )
    manifest = _manifest()
    manifest["download"]["sourceUrl"] = str(source)
    manifest["download"]["expectedFormat"] = "geojson"
    manifest["download"]["compression"] = "none"
    manifest["validation"] = {
        "minFeatureCount": 1,
        "bboxMustIntersect": [-125.0, 24.0, -66.0, 49.0],
    }
    plan = build_ingestion_plan(manifest)

    try:
        execute_ingestion_plan(plan, workspace_root=tmp_path)
    except RuntimeError as exc:
        assert "does not intersect" in str(exc)
    else:
        raise AssertionError("Non-intersecting bbox did not fail ingestion.")


###############################################################################
def test_dataset_materialization_fixtures_produce_normalized_indexes_tiles_and_health(tmp_path) -> None:
    fixture_root = Path(__file__).resolve().parents[1] / "fixtures/geospatial"
    cases = [
        (
            "natural_earth_admin_boundaries",
            fixture_root / "natural_earth_admin_boundaries.geojson",
            "geojson",
            "Polygon",
            "ne_id",
        ),
        (
            "census_cartographic_boundaries",
            fixture_root / "census_cartographic_boundary.geojson",
            "geojson",
            "Polygon",
            "GEOID",
        ),
        (
            "openaddresses_points",
            fixture_root / "openaddresses_points.csv",
            "csv",
            "Point",
            "id",
        ),
        (
            "overture_maps_places",
            fixture_root / "overture_places.geojson",
            "geojson",
            "Point",
            "id",
        ),
        (
            "ourairports_airports",
            fixture_root / "ourairports_airports.csv",
            "csv",
            "Point",
            "id",
        ),
        (
            "local_parcel_template",
            fixture_root / "local_parcel_template.geojson",
            "geojson",
            "Polygon",
            "parcel_id",
        ),
    ]

    for capability_id, source, expected_format, geometry_type, id_field in cases:
        manifest = _manifest()
        manifest["id"] = capability_id
        manifest["download"]["sourceUrl"] = str(source)
        manifest["download"]["expectedFormat"] = expected_format
        manifest["download"]["compression"] = "none"
        manifest["storage"] = {
            "rawPath": f"data/geospatial/raw/{capability_id}/",
            "normalizedPath": f"data/geospatial/normalized/{capability_id}/",
            "tilePath": f"data/geospatial/tiles/{capability_id}/",
        }
        manifest["normalization"] = {
            "targetCrs": "EPSG:4326",
            "geometryType": geometry_type,
            "idField": id_field,
            "fieldMap": {},
        }
        manifest["validation"] = {"minFeatureCount": 1}
        result = execute_ingestion_plan(
            build_ingestion_plan(manifest), workspace_root=tmp_path
        )

        assert result.feature_count >= 1
        assert result.normalized_file is not None
        assert result.spatial_index_file is not None
        assert result.text_index_file is not None
        assert result.tile_manifest_file is not None
        normalized = json.loads(Path(result.normalized_file).read_text(encoding="utf-8"))
        spatial_index = json.loads(Path(result.spatial_index_file).read_text(encoding="utf-8"))
        text_index = json.loads(Path(result.text_index_file).read_text(encoding="utf-8"))
        tile_manifest = json.loads(Path(result.tile_manifest_file).read_text(encoding="utf-8"))
        health = json.loads(Path(result.health_file).read_text(encoding="utf-8"))

        assert normalized["type"] == "FeatureCollection"
        assert normalized["features"]
        assert spatial_index["indexType"] == "bbox-summary"
        assert text_index["indexType"] == "term-to-feature"
        assert tile_manifest["capabilityId"] == capability_id
        assert tile_manifest["featureCount"] == result.feature_count
        assert health["status"] == "functional"
        assert health["featureCount"] == result.feature_count
