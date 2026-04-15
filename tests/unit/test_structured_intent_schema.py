from __future__ import annotations

from AEGIS.server.services.llm.structured import normalize_structured_payload


def test_structured_intent_defaults() -> None:
    normalized = normalize_structured_payload({})
    assert normalized["location"]["address"] is None
    assert normalized["base_map_type"] is None
    assert normalized["certainty"] == 0.0


def test_structured_intent_normalization() -> None:
    normalized = normalize_structured_payload(
        {
            "location": {"address": "Rome"},
            "coordinates": {"latitude": 41.9, "longitude": 12.5},
            "filters": ["openaq_air_quality"],
            "certainty": 0.7,
        }
    )
    assert normalized["location"]["address"] == "Rome"
    assert normalized["coordinates"]["latitude"] == 41.9
    assert normalized["filters"] == ["openaq_air_quality"]
