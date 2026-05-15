from __future__ import annotations

from server.services.geospatial.search_index import IndexedFeature, deduplicate_features


def test_geospatial_poi_deduplication_uses_coordinate_name_and_category() -> None:
    features = [
        IndexedFeature(id="a", label="Central Museum", category="tourism", latitude=41.9, longitude=12.5),
        IndexedFeature(id="b", label="central museum", category="tourism", latitude=41.9000001, longitude=12.5000001),
        IndexedFeature(id="c", label="Central Museum", category="charging", latitude=41.9, longitude=12.5),
    ]

    deduped = deduplicate_features(features)

    assert [feature.id for feature in deduped] == ["a", "c"]
