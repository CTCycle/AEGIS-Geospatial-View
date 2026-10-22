from __future__ import annotations
import hashlib
import json
import pytest
import io
import zipfile
from pathlib import Path
from server.services.geospatial.ingestion import IngestionManifestError, build_ingestion_plan, execute_ingestion_plan, validate_ingestion_manifest
from server.services.geospatial.materialization_runner import materialize_datasets
from tests.conftest import run_async_in_thread
from server.services.geospatial.providers.base import ProviderRequest, ProviderUnavailableError
from server.services.geospatial.providers.openchargemap import OpenChargeMapProvider
from server.services.geospatial.providers.overture import OvertureProvider
from datetime import UTC, datetime
from server.services.geospatial.providers.gtfs_realtime import GTFSRealtimeProvider
from server.services.geospatial.providers.gtfs_static import GTFSStaticProvider
from google.transit import gtfs_realtime_pb2

# --- test_geospatial_ingestion.py ---




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
    assert '"checksumSource": "checksumUrl"' in Path(result.metadata_file).read_text(
        encoding="utf-8"
    )

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
def _geojson_plan(tmp_path: Path, features: str, validation: dict, **download):
    source = tmp_path / "source.geojson"
    source.write_text(
        '{"type":"FeatureCollection","features":[' + features + "]}",
        encoding="utf-8",
    )
    manifest = _manifest()
    manifest["download"].update(
        {"sourceUrl": str(source), "expectedFormat": "geojson", "compression": "none"}
        | download
    )
    manifest["validation"] = validation
    return build_ingestion_plan(manifest)

_OUTSIDE_POINT = (
    '{"type":"Feature","id":"p","properties":{},'
    '"geometry":{"type":"Point","coordinates":[7.0,45.0]}}'
)

###############################################################################
def _snapshot(tmp_path: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(tmp_path)): path.read_bytes()
        for path in (tmp_path / "data").rglob("*")
        if path.is_file()
    }

###############################################################################
@pytest.mark.parametrize(
    ("features", "validation", "download", "message"),
    [
        ("", {"minFeatureCount": 0}, {"checksumSha256": "0" * 64}, "Checksum mismatch"),
        ("", {"minFeatureCount": 1}, {}, "expected at least"),
        (
            _OUTSIDE_POINT,
            {"minFeatureCount": 1, "bboxMustIntersect": [-125.0, 24.0, -66.0, 49.0]},
            {},
            "does not intersect",
        ),
    ],
)
def test_failed_ingestion_leaves_no_artifacts_behind(
    tmp_path, features, validation, download, message
) -> None:
    plan = _geojson_plan(tmp_path, features, validation, **download)

    with pytest.raises(RuntimeError, match=message):
        execute_ingestion_plan(plan, workspace_root=tmp_path)

    assert not (tmp_path / "data").exists()

###############################################################################
def test_unsupported_heavy_format_keeps_raw_artifact_and_reports_partial(tmp_path) -> None:
    source = tmp_path / "boundaries.shp"
    source.write_bytes(b"not-a-real-shapefile")
    manifest = _manifest()
    manifest["download"]["sourceUrl"] = str(source)
    manifest["download"]["compression"] = "none"
    manifest["validation"] = {
        "minFeatureCount": 1,
        "bboxMustIntersect": [-180.0, -90.0, 180.0, 90.0],
    }

    result = execute_ingestion_plan(
        build_ingestion_plan(manifest), workspace_root=tmp_path
    )

    assert result.normalized_file is None
    assert Path(result.raw_file).read_bytes() == b"not-a-real-shapefile"
    assert "optional geospatial ingestion dependencies" in result.warnings[0]
    assert json.loads(Path(result.health_file).read_text(encoding="utf-8"))["status"] == "partial"

###############################################################################
def test_failed_reingestion_restores_previous_materialization(tmp_path) -> None:
    good = _geojson_plan(tmp_path, _OUTSIDE_POINT, {"minFeatureCount": 1})
    execute_ingestion_plan(good, workspace_root=tmp_path)
    before = _snapshot(tmp_path)
    assert before

    failing = _geojson_plan(tmp_path, "", {"minFeatureCount": 1})
    with pytest.raises(RuntimeError, match="expected at least"):
        execute_ingestion_plan(failing, workspace_root=tmp_path)

    assert _snapshot(tmp_path) == before

###############################################################################
def test_dataset_materialization_fixtures_produce_normalized_indexes_tiles_and_health(
    tmp_path,
) -> None:
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
        normalized = json.loads(
            Path(result.normalized_file).read_text(encoding="utf-8")
        )
        spatial_index = json.loads(
            Path(result.spatial_index_file).read_text(encoding="utf-8")
        )
        text_index = json.loads(
            Path(result.text_index_file).read_text(encoding="utf-8")
        )
        tile_manifest = json.loads(
            Path(result.tile_manifest_file).read_text(encoding="utf-8")
        )
        health = json.loads(Path(result.health_file).read_text(encoding="utf-8"))

        assert normalized["type"] == "FeatureCollection"
        assert normalized["features"]
        assert spatial_index["indexType"] == "bbox-summary"
        assert text_index["indexType"] == "term-to-feature"
        assert tile_manifest["capabilityId"] == capability_id
        assert tile_manifest["featureCount"] == result.feature_count
        assert health["status"] == "functional"
        assert health["featureCount"] == result.feature_count

# --- test_geospatial_materialization_runner.py ---



###############################################################################
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

###############################################################################
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

# --- test_geospatial_infrastructure_sources.py ---



###############################################################################
def test_openchargemap_infrastructure_source_normalizes_live_station() -> None:
    async def fetcher(url, headers):
        del url, headers
        return [
            {
                "ID": 1,
                "AddressInfo": {
                    "Title": "Fast Charge",
                    "Latitude": 41.9,
                    "Longitude": 12.5,
                    "AddressLine1": "1 Main St",
                },
            }
        ]

    response = run_async_in_thread(
        OpenChargeMapProvider(api_key="ocm-key", fetcher=fetcher).fetch(
            ProviderRequest(
                capability_id="openchargemap_ev_charging",
                params={"latitude": 41.9, "longitude": 12.5, "live": True},
            )
        )
    )

    assert response.payload["features"][0]["category"] == "ev_charging"
    assert response.payload["features"][0]["source"] == "openchargemap"

###############################################################################
def test_overture_maps_queries_ingested_places_index(tmp_path) -> None:
    index = tmp_path / "places.geojson"
    index.write_text(
        '{"type":"FeatureCollection","features":[{"type":"Feature","id":"p1","properties":{"name":"Clinic","category":"healthcare"},"geometry":{"type":"Point","coordinates":[12.5,41.9]}}]}',
        encoding="utf-8",
    )
    response = run_async_in_thread(
        OvertureProvider(places_path=index).fetch(
            ProviderRequest(capability_id="overture_maps_places", bbox=(12, 41, 13, 42))
        )
    )

    assert response.payload["features"][0]["source"] == "overture"
    assert response.payload["totalResults"] == 1

###############################################################################
def test_overture_maps_can_augment_local_places_with_overpass_and_deduplicate(
    tmp_path,
) -> None:
    index = tmp_path / "places.geojson"
    index.write_text(
        '{"type":"FeatureCollection","features":[{"type":"Feature","id":"overture-1","properties":{"name":"Cafe Roma","category":"cafe"},"geometry":{"type":"Point","coordinates":[12.5,41.9]}}]}',
        encoding="utf-8",
    )

    ###############################################################################
    class _FakeOverpass:
        default_radius_m = 500.0

        # -------------------------------------------------------------------------
        async def get_nearby_poi(self, **kwargs):  # noqa: ANN003
            assert kwargs["latitude"] == 41.9
            assert kwargs["longitude"] == 12.5
            return {
                "items": [
                    {
                        "id": "node-1",
                        "name": "Cafe Roma",
                        "amenity": "cafe",
                        "latitude": 41.9,
                        "longitude": 12.5,
                    }
                ]
            }

    response = run_async_in_thread(
        OvertureProvider(places_path=index, overpass_service=_FakeOverpass()).fetch(
            ProviderRequest(
                capability_id="overture_maps_places",
                bbox=(12, 41, 13, 42),
                params={
                    "augment_overpass": True,
                    "latitude": 41.9,
                    "longitude": 12.5,
                },
            )
        )
    )

    assert response.payload["augmentation"] == "overpass"
    assert response.payload["totalResults"] == 1
    assert "© OpenStreetMap contributors (ODbL)" in response.attribution

# --- test_gtfs_providers.py ---




###############################################################################
def _gtfs_zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "stops.txt",
            "stop_id,stop_name,stop_lat,stop_lon\ns1,Central,41.9,12.5\n",
        )
        archive.writestr(
            "routes.txt",
            "route_id,route_short_name,route_long_name,route_type\nr1,10,Central Loop,3\n",
        )
        archive.writestr(
            "agency.txt",
            "agency_id,agency_name,agency_url,agency_timezone\n"
            "a1,Metro Test,https://example.test,Europe/Rome\n",
        )
        archive.writestr(
            "calendar.txt",
            "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\n"
            "wk,1,1,1,1,1,0,0,20260101,20261231\n",
        )
        archive.writestr(
            "shapes.txt",
            "shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence\n"
            "sh1,41.9,12.5,1\n"
            "sh1,42.0,12.6,2\n",
        )
    return buffer.getvalue()

###############################################################################
def test_gtfs_static_provider_normalizes_stops_routes_and_shapes() -> None:
    response = run_async_in_thread(
        GTFSStaticProvider().fetch(
            ProviderRequest(
                capability_id="gtfs_static",
                params={"feed_bytes": _gtfs_zip()},
            )
        )
    )

    assert response.payload["renderingMode"] == "clustered-points"
    assert response.payload["stops"][0]["name"] == "Central"
    assert response.payload["routes"][0]["shortName"] == "10"
    assert response.payload["agency"][0]["name"] == "Metro Test"
    assert response.payload["calendar"][0]["days"]["monday"] is True
    assert response.payload["shapes"][0]["geometry"]["type"] == "LineString"
    assert response.payload["summary"]["shapePointCount"] == 2

###############################################################################
def test_gtfs_static_provider_rejects_bad_zip() -> None:
    with pytest.raises(ProviderUnavailableError):
        run_async_in_thread(
            GTFSStaticProvider().fetch(
                ProviderRequest(
                    capability_id="gtfs_static",
                    params={"feed_bytes": b"not-a-zip"},
                )
            )
        )

###############################################################################
def test_gtfs_realtime_provider_normalizes_decoded_feed() -> None:
    now = int(datetime.now(UTC).timestamp())
    response = run_async_in_thread(
        GTFSRealtimeProvider().fetch(
            ProviderRequest(
                capability_id="gtfs_realtime",
                params={
                    "decoded_feed": {
                        "header": {"timestamp": now},
                        "entities": [
                            {
                                "vehicle": {
                                    "id": "v1",
                                    "tripId": "t1",
                                    "routeId": "r1",
                                    "position": {
                                        "latitude": 41.9,
                                        "longitude": 12.5,
                                    },
                                }
                            },
                            {"alert": {"effect": "DETOUR"}},
                            {"tripUpdate": {"tripId": "t2"}},
                        ],
                    }
                },
            )
        )
    )

    assert response.payload["renderingMode"] == "clustered-points"
    assert response.payload["vehicles"][0]["id"] == "v1"
    assert response.payload["summary"] == {
        "vehicleCount": 1,
        "renderedVehicleCount": 1,
        "alertCount": 1,
        "tripUpdateCount": 1,
    }
    assert response.payload["feedTimestamp"]
    assert response.payload["vehicleRenderingAllowed"] is True

###############################################################################
def test_gtfs_realtime_provider_suppresses_stale_vehicle_rendering() -> None:
    response = run_async_in_thread(
        GTFSRealtimeProvider().fetch(
            ProviderRequest(
                capability_id="gtfs_realtime",
                params={
                    "decoded_feed": {
                        "header": {"timestamp": 946684800},
                        "entities": [
                            {
                                "vehicle": {
                                    "id": "v1",
                                    "position": {
                                        "latitude": 41.9,
                                        "longitude": 12.5,
                                    },
                                }
                            }
                        ],
                    },
                    "feed_freshness_seconds": 120,
                },
            )
        )
    )

    assert response.payload["summary"]["vehicleCount"] == 1
    assert response.payload["summary"]["renderedVehicleCount"] == 0
    assert response.payload["vehicles"] == []
    assert response.payload["vehicleRenderingAllowed"] is False

# --- test_gtfs_realtime_alerts.py ---



###############################################################################
def test_gtfs_realtime_alerts_render_popup_fields() -> None:
    response = run_async_in_thread(
        GTFSRealtimeProvider().fetch(
            ProviderRequest(
                capability_id="gtfs_realtime",
                params={
                    "decoded_feed": {
                        "header": {"timestamp": 946684800},
                        "entities": [
                            {
                                "alert": {
                                    "cause": "CONSTRUCTION",
                                    "effect": "DETOUR",
                                    "header": "Route detour",
                                    "description": "Use alternate stop.",
                                    "activePeriods": [{"start": 1, "end": 2}],
                                }
                            }
                        ],
                    }
                },
            )
        )
    )

    alert = response.payload["alerts"][0]
    assert alert["cause"] == "CONSTRUCTION"
    assert alert["effect"] == "DETOUR"
    assert alert["header"] == "Route detour"
    assert alert["description"] == "Use alternate stop."
    assert alert["activePeriodCount"] == 1

# --- test_gtfs_realtime_provider.py ---



###############################################################################
def test_gtfs_realtime_provider_normalizes_trip_updates_alerts_and_vehicles() -> None:
    now = int(datetime.now(UTC).timestamp())

    response = run_async_in_thread(
        GTFSRealtimeProvider().fetch(
            ProviderRequest(
                capability_id="gtfs_realtime",
                params={
                    "decoded_feed": {
                        "header": {"timestamp": now},
                        "entities": [
                            {"tripUpdate": {"tripId": "trip-1", "routeId": "r1"}},
                            {"alert": {"effect": "DELAY", "header": "Delay"}},
                            {
                                "vehicle": {
                                    "id": "vehicle-1",
                                    "routeId": "r1",
                                    "position": {"latitude": 41.9, "longitude": 12.5},
                                }
                            },
                        ],
                    }
                },
            )
        )
    )

    assert response.payload["summary"]["tripUpdateCount"] == 1
    assert response.payload["summary"]["alertCount"] == 1
    assert response.payload["summary"]["vehicleCount"] == 1
    assert response.payload["vehicleRenderingAllowed"] is True

###############################################################################
def test_gtfs_realtime_provider_fetches_configured_protobuf_feed_url() -> None:
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    feed.header.timestamp = int(datetime.now(UTC).timestamp())
    entity = feed.entity.add()
    entity.id = "alert-1"
    entity.alert.effect = gtfs_realtime_pb2.Alert.DETOUR
    feed_bytes = feed.SerializeToString()
    calls: list[str] = []

    async def fetcher(url: str, headers: dict[str, str] | None = None) -> bytes:
        calls.append(url)
        return feed_bytes

    response = run_async_in_thread(
        GTFSRealtimeProvider(fetcher=fetcher).fetch(
            ProviderRequest(
                capability_id="gtfs_realtime",
                params={"feed_url": "https://agency.example/gtfs-rt.pb"},
            )
        )
    )

    assert calls == ["https://agency.example/gtfs-rt.pb"]
    assert response.payload["feedUrl"] == "https://agency.example/gtfs-rt.pb"
    assert response.payload["summary"]["alertCount"] == 1

# --- test_gtfs_static_ingestion.py ---



###############################################################################
def _sample_gtfs_static_zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "stops.txt", "stop_id,stop_name,stop_lat,stop_lon\ns1,Central,41.9,12.5\n"
        )
        archive.writestr(
            "routes.txt",
            "route_id,route_short_name,route_long_name,route_type\nr1,10,Central Loop,3\n",
        )
        archive.writestr(
            "agency.txt",
            "agency_id,agency_name,agency_url,agency_timezone\na1,Metro Test,https://example.test,Europe/Rome\n",
        )
        archive.writestr(
            "calendar.txt",
            "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\nwk,1,1,1,1,1,0,0,20260101,20261231\n",
        )
        archive.writestr(
            "shapes.txt",
            "shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence\nsh1,41.9,12.5,1\nsh1,42.0,12.6,2\n",
        )
    return buffer.getvalue()

###############################################################################
def test_gtfs_static_provider_fetches_configured_feed_url() -> None:
    calls: list[str] = []

    async def fetcher(url: str, headers: dict[str, str] | None = None) -> bytes:
        calls.append(url)
        return _sample_gtfs_static_zip()

    response = run_async_in_thread(
        GTFSStaticProvider(fetcher=fetcher).fetch(
            ProviderRequest(
                capability_id="gtfs_static",
                params={"feed_url": "https://agency.example/gtfs.zip"},
            )
        )
    )

    assert calls == ["https://agency.example/gtfs.zip"]
    assert response.payload["feedUrl"] == "https://agency.example/gtfs.zip"
    assert response.payload["summary"]["stopCount"] == 1