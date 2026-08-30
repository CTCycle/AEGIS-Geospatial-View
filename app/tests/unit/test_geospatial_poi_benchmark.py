from __future__ import annotations

from server.services.geospatial.poi_benchmark import (
    benchmark_poi_parity,
    load_poi_records,
)


###############################################################################
def test_poi_parity_report_matches_by_id_and_tracks_completeness() -> None:
    baseline = [
        {"id": "a", "name": "Clinic", "latitude": 41.9, "longitude": 12.5},
        {"id": "b", "name": "Museum", "latitude": 41.91, "longitude": 12.51},
    ]
    candidate = [
        {"id": "a", "name": "Clinic", "latitude": 41.9, "longitude": 12.5},
        {"id": "b", "name": "Museum", "latitude": 41.91, "longitude": 12.51},
    ]

    report = benchmark_poi_parity(baseline, candidate)

    assert report.matched_count == 2
    assert report.recall == 1.0
    assert report.precision == 1.0
    assert report.meets_thresholds is True


###############################################################################
def test_poi_parity_report_rejects_missing_candidate_coverage_and_duplicates() -> None:
    baseline = [
        {"id": "a", "name": "Clinic", "latitude": 41.9, "longitude": 12.5},
        {"id": "b", "name": "Museum", "latitude": 41.91, "longitude": 12.51},
    ]
    candidate = [
        {"id": "x", "name": "Clinic", "latitude": 41.9, "longitude": 12.5},
        {"id": "y", "name": "Clinic", "latitude": 41.9, "longitude": 12.5},
    ]

    report = benchmark_poi_parity(baseline, candidate)

    assert report.recall == 0.5
    assert report.duplicate_rate == 0.5
    assert report.meets_thresholds is False


###############################################################################
def test_load_poi_records_accepts_geojson_feature_collections(tmp_path) -> None:
    source = tmp_path / "provider.geojson"
    source.write_text(
        '{"type":"FeatureCollection","features":[{"type":"Feature","id":"p1","properties":{"name":"Clinic"},"geometry":{"type":"Point","coordinates":[12.5,41.9]}}]}',
        encoding="utf-8",
    )

    records = load_poi_records(source)

    assert records == [
        {
            "id": "p1",
            "name": "Clinic",
            "category": None,
            "latitude": 41.9,
            "longitude": 12.5,
        }
    ]
