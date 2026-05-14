from __future__ import annotations

from server.services.geospatial.search_index import (
    IndexedFeature,
    build_feature_search_index,
    query_search_index,
)


def test_geospatial_poi_search_index_matches_labels_categories_and_sources() -> None:
    index = build_feature_search_index(
        [
            IndexedFeature(id="1", label="Central Museum", category="tourism", source="opentripmap"),
            IndexedFeature(id="2", label="Fast Charge", category="ev_charging", source="openchargemap"),
        ]
    )

    assert [item.id for item in query_search_index(index, "museum tourism")] == ["1"]
    assert [item.id for item in query_search_index(index, "ev charging")] == ["2"]
