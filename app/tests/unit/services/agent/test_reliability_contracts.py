from __future__ import annotations

from server.domain.agent.extraction_schemas import LLMParserExtraction
from server.services.agent.parser_service import ParserService
from server.services.geospatial.overpass import OverpassService


###############################################################################
def test_conceptual_basemap_question_is_not_a_map_fallback() -> None:
    extracted = ParserService._apply_domain_rules(
        "What is the difference between a map layer and a basemap?",
        LLMParserExtraction(
            task_class="general_question",
            action_id="chat_response",
            action_label="General question",
            task_tags=["chat"],
            requires_location=False,
            direct_response_sufficient=True,
        ),
        {},
    )

    assert extracted.task_class == "general_question"
    assert extracted.location_signals == []


###############################################################################
def test_explicit_no_map_request_is_direct_and_poi_categories_are_typed() -> None:
    text = (
        "Give me the coordinates of Cape Town, South Africa, and do not render a map."
    )
    extracted = ParserService._apply_domain_rules(
        text,
        LLMParserExtraction(
            task_class="direct_query",
            action_id="location_to_coordinates",
            action_label="Location lookup",
            task_tags=["coordinates"],
            action_tags=["direct"],
            requires_location=True,
            direct_response_sufficient=True,
            location_signals=[
                {
                    "signal_type": "city",
                    "raw_value": "Cape Town, South Africa",
                    "normalized_value": "Cape Town, South Africa",
                }
            ],
        ),
        {},
    )

    assert extracted.task_class == "direct_query"
    assert extracted.requested_basemap is None
    assert extracted.requested_layers == []

    poi_text = "Show bicycle parking and rail stations around Tokyo Station."
    poi = ParserService._apply_domain_rules(
        poi_text,
        LLMParserExtraction(
            task_class="map_search",
            action_id="map_search",
            action_label="Nearby places",
            task_tags=["map", "poi"],
            requires_location=True,
            poi_categories=["bicycle_parking", "rail_stations"],
        ),
        {},
    )
    assert poi.poi_categories == ["bicycle_parking", "rail_stations"]


###############################################################################
def test_overpass_category_selectors_cover_public_transit_and_rail() -> None:
    service = OverpassService(base_url="https://example.test")
    selectors = [
        selector
        for category in ("transit_stops", "rail_stations")
        for selector in service.CATEGORY_SELECTORS[category]
    ]

    assert ("public_transport", "platform") in selectors
    assert ("highway", "bus_stop") in selectors
    assert ("railway", "station") in selectors
