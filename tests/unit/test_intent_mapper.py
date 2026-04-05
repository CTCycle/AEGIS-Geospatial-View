from __future__ import annotations

from AEGIS.server.services.search.intent_mapper import map_structured_intent_to_location_request


def test_intent_mapper_supports_coordinates_and_filters() -> None:
    mapped = map_structured_intent_to_location_request(
        {
            "location": {"name": "Rome, Italy", "coordinates": {"latitude": 41.9, "longitude": 12.5}},
            "map_preferences": {"overlay_candidates": ["openaq_air_quality"]},
            "base_map": "osm_default",
            "temporal_context": {"normalized_datetime": "2026-01-01T00:00:00Z"},
        }
    )
    assert mapped["use_coordinates"] is True
    assert mapped["latitude"] == 41.9
    assert mapped["longitude"] == 12.5
    assert mapped["overlay_ids"] == ["openaq_air_quality"]
    assert mapped["filters"] == ["openaq_air_quality"]


def test_intent_mapper_uses_bbox_when_present() -> None:
    mapped = map_structured_intent_to_location_request(
        {
            "location": {"name": "Berlin", "bbox": [13.0, 52.3, 13.8, 52.7]},
            "map_preferences": {"overlay_candidates": ["eea_noise_2019"]},
            "temporal_context": {"normalized_datetime": "2026-01-01T00:00:00Z"},
        }
    )
    assert mapped["bbox"] == [13.0, 52.3, 13.8, 52.7]
