from __future__ import annotations

from AEGIS.server.services.search.intent_mapper import map_structured_intent_to_location_request


def test_intent_mapper_supports_coordinates_and_filters() -> None:
    mapped = map_structured_intent_to_location_request(
        extracted_state={
            "location": {"address": "Rome, Italy"},
            "coordinates": {"latitude": 41.9, "longitude": 12.5},
            "filters": ["openaq_air_quality"],
        },
        user_message="rome",
        selected_basemap_id="osm_default",
        selected_overlay_ids=["openaq_air_quality"],
        fallback_datetime="2026-01-01T00:00:00Z",
    )
    assert mapped["use_coordinates"] is True
    assert mapped["latitude"] == 41.9
    assert mapped["longitude"] == 12.5
    assert mapped["overlay_ids"] == ["openaq_air_quality"]
    assert mapped["filters"] == []
    assert mapped["semantic_filters"] == ["openaq_air_quality"]


def test_intent_mapper_uses_bbox_when_present() -> None:
    mapped = map_structured_intent_to_location_request(
        extracted_state={
            "location": {"address": "Berlin"},
            "coordinates": {"latitude": None, "longitude": None},
            "filters": ["eea_noise_2019"],
        },
        user_message="berlin",
        selected_basemap_id="osm_default",
        selected_overlay_ids=["eea_noise_2019"],
        fallback_datetime="2026-01-01T00:00:00Z",
    )
    assert mapped["address"] == "Berlin"
