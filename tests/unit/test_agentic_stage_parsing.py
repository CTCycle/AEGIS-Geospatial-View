from __future__ import annotations

from AEGIS.server.domain.extraction.models import StageAParserIntent
from AEGIS.server.services.agent.parser_service import ParserService
from AEGIS.server.services.llm.structured import (
    normalize_stage_a_payload,
    normalize_stage_b_payload,
)


def test_stage_a_normalization_coerces_aliases_and_types() -> None:
    normalized = normalize_stage_a_payload(
        {
            "hasLocation": "true",
            "location_type": "city",
            "hasTimeReference": "0",
            "search_required": "1",
            "data_required": False,
            "tools": "map_search, get_weather_forecast",
            "confidence": "0.82",
        }
    )
    assert normalized["has_location"] is True
    assert normalized["has_time_reference"] is False
    assert normalized["requires_search"] is True
    assert normalized["required_tools"] == ["map_search", "get_weather_forecast"]
    assert normalized["certainty"] == 0.82


def test_stage_b_normalization_accepts_basemap_overlay_aliases() -> None:
    normalized = normalize_stage_b_payload(
        {
            "location": {"city": "Rome"},
            "coordinates": {"latitude": "41.9", "longitude": "12.5"},
            "time_reference": None,
            "basemap": "osm_default",
            "overlays": "openmeteo_weather_forecast, overpass_poi_amenities",
        }
    )
    assert normalized["location"]["city"] == "Rome"
    assert normalized["coordinates"]["latitude"] == 41.9
    assert normalized["base_map"] == "osm_default"
    assert normalized["required_overlays"] == [
        "openmeteo_weather_forecast",
        "overpass_poi_amenities",
    ]


def test_parser_stage_a_fallback_applies_when_provider_unavailable() -> None:
    class _FailingFactory:
        def get_parser_provider(self, provider: str):  # noqa: ARG002
            raise RuntimeError("parser unavailable")

    service = ParserService(
        llm_factory=_FailingFactory(), provider="ollama", model="llama3.2"
    )
    stage_a = service.parse_stage_a_intent(
        conversation_context="# message 1\nshow map in Rome",
        user_message="show map in Rome",
        available_tools=[],
        certainty_threshold=0.75,
        max_retries=2,
    )
    assert isinstance(stage_a, StageAParserIntent)
    assert stage_a.has_location is True
    assert stage_a.requires_search is True
