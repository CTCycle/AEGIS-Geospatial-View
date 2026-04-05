from __future__ import annotations

from AEGIS.server.services.llm.structured import normalize_structured_payload


def test_structured_intent_defaults() -> None:
    normalized = normalize_structured_payload({})
    assert normalized["location"]["is_partial"] is False
    assert normalized["map_preferences"]["map_type"] == "auto"
    assert normalized["planning"]["confidence"] == 0.0


def test_structured_intent_legacy_normalization() -> None:
    normalized = normalize_structured_payload(
        {
            "location_text": "Rome",
            "coordinates": {"latitude": 41.9, "longitude": 12.5},
            "search_radius_m": 1000,
            "requested_overlays": ["openaq_air_quality"],
            "datetime_inference": "2026-01-01T00:00:00Z",
        }
    )
    assert normalized["location"]["name"] == "Rome"
    assert normalized["location"]["coordinates"]["latitude"] == 41.9
    assert normalized["map_preferences"]["overlay_candidates"] == ["openaq_air_quality"]
