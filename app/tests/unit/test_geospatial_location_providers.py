from __future__ import annotations
from datetime import UTC, datetime
from tests.conftest import run_async_in_thread
from server.services.geospatial.nominatim import NominatimService
import pytest
from pydantic import ValidationError
from server.contracts.geospatial import LocationSearchRequest

# --- test_nominatim_service.py ---




###############################################################################
def test_nominatim_rank_candidates_prefers_poi_when_expected() -> None:
    service = NominatimService(user_agent="test-suite", timeout=0.1)
    candidates = [
        {
            "lat": "41.8933",
            "lon": "12.4829",
            "display_name": "Rome, Lazio, Italy",
            "class": "boundary",
            "type": "administrative",
            "importance": 0.9,
            "boundingbox": ["41.7", "42.0", "12.2", "12.8"],
            "address": {"city": "Rome", "country": "Italy"},
        },
        {
            "lat": "41.8902",
            "lon": "12.4922",
            "display_name": "Colosseum, Piazza del Colosseo, Roma, Italia",
            "class": "tourism",
            "type": "attraction",
            "importance": 0.8,
            "boundingbox": ["41.8895", "41.8907", "12.4912", "12.4931"],
            "address": {
                "road": "Piazza del Colosseo",
                "city": "Rome",
                "country": "Italy",
            },
        },
    ]
    ranked = service.rank_candidates(
        candidates,
        address="Colosseum",
        city="Rome",
        country_name="Italy",
        country_code="IT",
        query="Colosseum, Rome, Italy",
        expected_location_type="poi",
        fetched_at=datetime(2026, 9, 1, 10, 0, tzinfo=UTC),
    )
    assert ranked
    assert ranked[0]["selected_result_type"] == "attraction"
    assert ranked[0]["lat"] == 41.8902
    assert ranked[0]["provider"] == "nominatim"
    assert ranked[0]["source_url"].endswith("/search")
    assert ranked[0]["fetched_at"] == "2026-09-01T10:00:00+00:00"

###############################################################################
def test_nominatim_rank_candidates_preserves_named_river_semantics() -> None:
    service = NominatimService(user_agent="test-suite", timeout=0.1)
    ranked = service.rank_candidates(
        [
            {
                "lat": "47.56",
                "lon": "7.59",
                "display_name": "Rhine, Basel, Switzerland",
                "class": "waterway",
                "type": "river",
                "importance": 0.8,
                "address": {"city": "Basel", "country": "Switzerland"},
            },
            {
                "lat": "47.56",
                "lon": "7.59",
                "display_name": "Basel, Switzerland",
                "class": "boundary",
                "type": "administrative",
                "importance": 0.95,
                "address": {"city": "Basel", "country": "Switzerland"},
            },
        ],
        address="Rhine river",
        city="Basel",
        country_name="Switzerland",
        country_code="CH",
        query="Rhine river, Basel, Switzerland",
        expected_location_type="river",
    )
    assert ranked
    assert ranked[0]["selected_result_type"] == "river"
    assert ranked[0]["selected_result_class"] == "waterway"

###############################################################################
def test_nominatim_rank_candidates_prefers_city_boundary_over_parent_region() -> None:
    service = NominatimService(user_agent="test-suite", timeout=0.1)
    candidates = [
        {
            "lat": "12.0",
            "lon": "45.0",
            "display_name": "Coastal Province, Republicland",
            "class": "administrative",
            "type": "administrative",
            "importance": 0.95,
            "address": {
                "state": "Coastal Province",
                "country": "Republicland",
            },
        },
        {
            "lat": "12.3",
            "lon": "45.6",
            "display_name": "Harborview, Coastal Province, Republicland",
            "class": "administrative",
            "type": "administrative",
            "importance": 0.65,
            "address": {
                "city": "Harborview",
                "state": "Coastal Province",
                "country": "Republicland",
            },
        },
    ]

    ranked = service.rank_candidates(
        candidates,
        address="Harborview, Republicland",
        city=None,
        country_name=None,
        country_code=None,
        query="Harborview, Republicland",
        expected_location_type="city",
    )

    assert ranked[0]["lat"] == 12.3

###############################################################################
def test_nominatim_uses_localized_city_name_metadata_before_parent_result() -> None:
    service = NominatimService(user_agent="test-suite", timeout=0.1)
    ranked = service.rank_candidates(
        [
            {
                "lat": "19.32",
                "lon": "-99.15",
                "display_name": "Mexico City, Mexico",
                "class": "boundary",
                "type": "state",
                "importance": 0.9,
                "address": {"state": "Mexico City", "country": "Mexico"},
                "namedetails": {"name": "Ciudad de México"},
            },
            {
                "lat": "19.43",
                "lon": "-99.13",
                "display_name": "Mexico City, Cuauhtémoc, Mexico",
                "class": "boundary",
                "type": "administrative",
                "importance": 0.7,
                "address": {
                    "city": "Mexico City",
                    "state": "Mexico City",
                    "country": "Mexico",
                },
                "namedetails": {"name": "Ciudad de México"},
            },
        ],
        address="Ciudad de México, México",
        city=None,
        country_name=None,
        country_code=None,
        query="Ciudad de México, México",
        expected_location_type="city",
    )

    assert ranked[0]["lat"] == 19.43

###############################################################################
def test_nominatim_surfaces_unqualified_same_level_city_ambiguity() -> None:
    service = NominatimService(user_agent="test-suite", timeout=0.1)

    ranked = [
        {
            "display_name": "San Jose, Northland",
            "lat": 10.0,
            "lon": 20.0,
            "confidence": 0.72,
            "selected_result_type": "city",
            "selected_result_class": "place",
        },
        {
            "display_name": "San Jose, Southland",
            "lat": 30.0,
            "lon": 40.0,
            # A geocoder ranking gap must not turn an unqualified city into a
            # silently selected target.
            "confidence": 0.18,
            "selected_result_type": "town",
            "selected_result_class": "place",
        },
    ]

    async def _run() -> None:
        result = service._find_ambiguous_candidates(
            ranked,
            expected_location_type="city",
            query="San Jose",
            has_parent_context=False,
        )
        assert [item["display_name"] for item in result] == [
            "San Jose, Northland",
            "San Jose, Southland",
        ]

    run_async_in_thread(_run())

###############################################################################
def test_nominatim_uses_structured_city_context_for_ambiguity_labels() -> None:
    service = NominatimService(user_agent="test-suite", timeout=0.1)
    ranked = [
        {
            "display_name": "Milano, Milam County, Texas, 76556, United States",
            "lat": 30.7,
            "lon": -96.5,
            "confidence": 0.78,
            "geocoder_importance": 0.55,
            "selected_result_type": "city",
            "selected_result_class": "place",
            "address": {
                "city": "Milano",
                "county": "Milam County",
                "state": "Texas",
                "country": "United States",
            },
        },
        {
            "display_name": "Milan, Rodano, Milan, Lombardy, Italy",
            "lat": 45.46,
            "lon": 9.19,
            "confidence": 0.77,
            "geocoder_importance": 0.54,
            "selected_result_type": "city",
            "selected_result_class": "place",
            "address": {
                "city": "Milan",
                "suburb": "Rodano",
                "state": "Lombardy",
                "country": "Italy",
            },
            "namedetails": {"name:it": "Milano"},
        },
    ]

    candidates = service._find_ambiguous_candidates(
        ranked,
        expected_location_type="city",
        query="Milano",
        has_parent_context=False,
    )

    assert [item["display_name"] for item in candidates] == [
        "Milano, Texas, United States",
        "Milan, Lombardy, Italy",
    ]

###############################################################################
def test_nominatim_accepts_a_dominant_unqualified_city_candidate() -> None:
    service = NominatimService(user_agent="test-suite", timeout=0.1)
    ranked = [
        {
            "display_name": "Rome, Lazio, Italy",
            "lat": 41.9,
            "lon": 12.5,
            "confidence": 0.84,
            "geocoder_importance": 0.86,
            "selected_result_type": "administrative",
            "selected_address_type": "city",
            "address": {"city": "Rome", "country": "Italy"},
        },
        {
            "display_name": "Rome, Georgia, United States",
            "lat": 34.2,
            "lon": -85.1,
            "confidence": 0.81,
            "geocoder_importance": 0.52,
            "selected_result_type": "administrative",
            "selected_address_type": "city",
            "address": {"city": "Rome", "country": "United States"},
        },
    ]

    assert service._find_ambiguous_candidates(
        ranked,
        expected_location_type="city",
        query="Rome",
        has_parent_context=False,
    ) == []

###############################################################################
def _city_candidate(name: str, region: str, country: str, *, lat: float, confidence: float, importance: float) -> dict[str, object]:
    return {
        "display_name": f"{name}, {region}, {country}",
        "lat": lat,
        "lon": 0.0,
        "confidence": confidence,
        "geocoder_importance": importance,
        "selected_result_type": "city",
        "selected_result_class": "place",
        "address": {"city": name, "state": region, "country": country},
    }


def test_nominatim_accepts_a_clearly_more_prominent_city_but_not_a_comparable_one() -> None:
    service = NominatimService(user_agent="test-suite", timeout=0.1)

    def ambiguous(first_importance: float, second_importance: float) -> list[dict[str, object]]:
        return service._find_ambiguous_candidates(
            [
                _city_candidate("Wellington", "Wellington", "New Zealand", lat=-41.3, confidence=0.75, importance=first_importance),
                _city_candidate("Wellington", "Texas", "United States", lat=34.8, confidence=0.7, importance=second_importance),
            ],
            expected_location_type="city",
            query="Wellington",
            has_parent_context=False,
        )

    assert ambiguous(0.66, 0.46) == []
    assert len(ambiguous(0.6, 0.55)) == 2

###############################################################################
def test_nominatim_does_not_rival_a_landmark_with_a_street_of_the_same_name() -> None:
    service = NominatimService(user_agent="test-suite", timeout=0.1)
    ranked = [
        {
            "display_name": "Brandenburger Tor, Berlin, Germany",
            "lat": 52.516,
            "lon": 13.378,
            "confidence": 0.7,
            "geocoder_importance": 0.6,
            "selected_result_type": "attraction",
            "selected_result_class": "tourism",
        },
        {
            "display_name": "Brandenburg Gate, Kaliningrad, Russia",
            "lat": 54.7,
            "lon": 20.5,
            "confidence": 0.7,
            "geocoder_importance": 0.55,
            "selected_result_type": "residential",
            "selected_result_class": "highway",
        },
    ]

    def ambiguous(expected: str) -> list[dict[str, object]]:
        return service._find_ambiguous_candidates(
            ranked, expected_location_type=expected, query="Brandenburg Gate", has_parent_context=False
        )

    assert ambiguous("landmark") == []
    assert len(ambiguous("street")) == 2

###############################################################################
@pytest.mark.parametrize(
    ("query", "major", "minor"),
    [
        (
            "Turin",
            ("Turin, Piedmont, Italy", "Italy", 0.77, ["44.99", "45.14", "7.58", "7.77"]),
            (
                "Turin, Belvidere Township, Monona County, Iowa, United States",
                "United States",
                0.459,
                ["42.0187", "42.0230", "-95.9692", "-95.9631"],
            ),
        ),
        (
            "Madrid",
            ("Madrid, Community of Madrid, Spain", "Spain", 0.819, ["40.31", "40.64", "-3.89", "-3.52"]),
            (
                "Madrid, Boone County, Iowa, United States",
                "United States",
                0.463,
                ["41.8668", "41.8854", "-93.8326", "-93.8132"],
            ),
        ),
    ],
)
def test_nominatim_prefers_prominent_city_over_same_name_small_place(
    query: str,
    major: tuple[str, str, float, list[str]],
    minor: tuple[str, str, float, list[str]],
) -> None:
    service = NominatimService(user_agent="test-suite", timeout=0.1)
    candidates = [
        {
            "lat": bbox[0],
            "lon": bbox[2],
            "display_name": display_name,
            "class": "boundary",
            "type": "administrative",
            "addresstype": address_type,
            "importance": importance,
            "boundingbox": bbox,
            "address": {address_type: query, "country": country},
        }
        for (display_name, country, importance, bbox), address_type in (
            (major, "city"),
            (minor, "hamlet"),
        )
    ]

    ranked = service.rank_candidates(
        candidates,
        address=query,
        city=None,
        country_name=None,
        country_code=None,
        query=query,
        expected_location_type="city",
    )

    assert ranked[0]["display_name"] == major[0]
    assert service._find_ambiguous_candidates(
        ranked,
        expected_location_type="city",
        query=query,
        has_parent_context=False,
    ) == []

###############################################################################
def test_nominatim_uses_exact_parent_for_qualified_city_ambiguity() -> None:
    service = NominatimService(user_agent="test-suite", timeout=0.1)
    ranked = [
        {
            "display_name": "Houston, Harris County, Texas, United States",
            "lat": 29.76,
            "lon": -95.37,
            "confidence": 0.76,
            "selected_result_type": "city",
            "address": {
                "city": "Houston",
                "county": "Harris County",
                "state": "Texas",
                "country": "United States",
            },
        },
        {
            "display_name": "Houston, Texas County, Missouri, United States",
            "lat": 37.33,
            "lon": -91.96,
            "confidence": 0.75,
            "selected_result_type": "city",
            "address": {
                "city": "Houston",
                "county": "Texas County",
                "state": "Missouri",
                "country": "United States",
            },
        },
    ]

    assert service._find_ambiguous_candidates(
        ranked,
        expected_location_type="city",
        query="Houston, Texas",
        has_parent_context=True,
    ) == []

###############################################################################
def test_nominatim_prioritizes_exact_qualified_city_parent() -> None:
    service = NominatimService(user_agent="test-suite", timeout=0.1)

    service.perform_request = lambda params: [  # type: ignore[method-assign]
        {
            "display_name": "Houston, Texas County, Missouri, United States",
            "lat": "37.33",
            "lon": "-91.96",
            "class": "place",
            "type": "city",
            "importance": 0.9,
            "address": {
                "city": "Houston",
                "county": "Texas County",
                "state": "Missouri",
                "country": "United States",
            },
        },
        {
            "display_name": "Houston, Harris County, Texas, United States",
            "lat": "29.76",
            "lon": "-95.37",
            "class": "place",
            "type": "city",
            "importance": 0.6,
            "address": {
                "city": "Houston",
                "county": "Harris County",
                "state": "Texas",
                "country": "United States",
            },
        },
    ]

    async def _run() -> None:
        result = await service.extract_coordinates(
            address="Houston",
            city=None,
            country_name="Texas",
            country_code=None,
            expected_location_type="city",
        )
        assert result is not None
        assert result["display_name"].startswith("Houston, Harris County, Texas")

    run_async_in_thread(_run())

###############################################################################
def test_nominatim_deduplicates_city_boundary_and_centroid() -> None:
    service = NominatimService(user_agent="test-suite", timeout=0.1)
    ranked = service.rank_candidates(
        [
            {
                "lat": "52.1975",
                "lon": "0.1391",
                "display_name": (
                    "Cambridge, Cambridgeshire, England, United Kingdom"
                ),
                "class": "boundary",
                "type": "administrative",
                "addresstype": "city",
                "importance": 0.85,
                "address": {
                    "city": "Cambridge",
                    "county": "Cambridgeshire",
                    "state": "England",
                    "country": "United Kingdom",
                },
            },
            {
                "lat": "52.2055",
                "lon": "0.1186",
                "display_name": (
                    "Cambridge, Cambridgeshire, England, CB2 3NR, United Kingdom"
                ),
                "class": "place",
                "type": "city",
                "addresstype": "city",
                "importance": 0.8,
                "address": {
                    "city": "Cambridge",
                    "county": "Cambridgeshire",
                    "state": "England",
                    "country": "United Kingdom",
                    "postcode": "CB2 3NR",
                },
            },
        ],
        address="Cambridge",
        city=None,
        country_name="United Kingdom",
        country_code="GB",
        query="Cambridge, United Kingdom",
        expected_location_type="city",
    )

    assert len(ranked) == 2
    assert "ambiguous_candidates" not in ranked[0]

###############################################################################
def test_nominatim_deduplicates_city_boundary_without_parent_fields() -> None:
    service = NominatimService(user_agent="test-suite", timeout=0.1)
    ranked = [
        {
            "display_name": "Ljubljana, Upravna Enota Ljubljana, Slovenia",
            "lat": 46.06005,
            "lon": 14.5911883,
            "selected_result_type": "administrative",
            "selected_address_type": "municipality",
            "address": {"municipality": "Ljubljana", "country": "Slovenia"},
            "confidence": 0.7898,
        },
        {
            "display_name": "Ljubljana, Upravna Enota Ljubljana, 1000, Slovenia",
            "lat": 46.0500268,
            "lon": 14.5069289,
            "selected_result_type": "city",
            "selected_address_type": "city",
            "address": {"city": "Ljubljana", "country": "Slovenia"},
            "confidence": 0.8074,
        },
    ]

    assert service._find_ambiguous_candidates(
        ranked,
        expected_location_type="city",
        query="Ljubljana, Slovenia",
        has_parent_context=True,
    ) == []

###############################################################################
def test_nominatim_prepares_language_and_name_metadata_for_validation() -> None:
    service = NominatimService(user_agent="test-suite", timeout=0.1)
    captured: dict[str, str] = {}

    def _perform_request(params: dict[str, str]) -> list[dict[str, object]]:
        captured.update(params)
        return [
            {
                "lat": "10.0",
                "lon": "20.0",
                "display_name": "Harborview, Countryland",
                "class": "place",
                "type": "city",
                "importance": 0.8,
                "address": {"city": "Harborview", "country": "Countryland"},
            }
        ]

    service.perform_request = _perform_request  # type: ignore[method-assign]

    async def _run() -> None:
        result = await service.extract_coordinates(
            address="Harborview",
            city=None,
            country_name="Countryland",
            country_code=None,
            expected_location_type="city",
        )
        assert result is not None
        assert result["lat"] == 10.0

    run_async_in_thread(_run())
    assert captured["namedetails"] == "1"
    assert captured["accept-language"] == "en"

###############################################################################
def test_nominatim_retries_generic_named_target_with_bounded_acronym_variant() -> None:
    service = NominatimService(user_agent="test-suite", timeout=0.1)
    queries: list[str] = []

    def _perform_request(params: dict[str, str]) -> list[dict[str, object]]:
        queries.append(params["q"])
        if params["q"].casefold().startswith("ncrc"):
            return [
                {
                    "lat": "52.2158",
                    "lon": "4.4165",
                    "display_name": "Northern Coastal Research Center, Noordwijk, Netherlands",
                    "class": "amenity",
                    "type": "research_institute",
                    "importance": 0.2,
                    "address": {"town": "Noordwijk", "country": "Netherlands"},
                    "namedetails": {"name": "Northern Coastal Research Center"},
                }
            ]
        return []

    service.perform_request = _perform_request  # type: ignore[method-assign]

    async def _run() -> None:
        result = await service.extract_coordinates(
            address="Northern Coastal Research Center facility",
            city="Noordwijk",
            country_name="Netherlands",
            country_code=None,
            expected_location_type="poi",
        )
        assert result is not None
        assert result["lat"] == 52.2158

    run_async_in_thread(_run())
    assert queries == [
        "Northern Coastal Research Center facility, Noordwijk, Netherlands",
        "northern coastal research center, Noordwijk, Netherlands",
        "ncrc, Noordwijk, Netherlands",
    ]

###############################################################################
def test_nominatim_retries_mount_feature_when_exact_results_are_pois() -> None:
    service = NominatimService(user_agent="test-suite", timeout=0.1)
    queries: list[str] = []

    def _perform_request(params: dict[str, str]) -> list[dict[str, object]]:
        queries.append(params["q"])
        if params["q"].casefold() == "mount kilimanjaro, tanzania":
            return [
                {
                    "lat": "-3.0674",
                    "lon": "37.3556",
                    "display_name": "Mount Kilimanjaro Primary School, Tanzania",
                    "class": "amenity",
                    "type": "school",
                    "importance": 0.2,
                    "address": {"country": "Tanzania"},
                }
            ]
        if params["q"].casefold() == "kilimanjaro, tanzania":
            return [
                {
                    "lat": "-3.0674",
                    "lon": "37.3556",
                    "display_name": "Kilimanjaro, Northern Zone, Tanzania",
                    "class": "natural",
                    "type": "massif",
                    "importance": 0.6,
                    "address": {
                        "state": "Kilimanjaro",
                        "country": "Tanzania",
                    },
                }
            ]
        return []

    service.perform_request = _perform_request  # type: ignore[method-assign]

    async def _run() -> None:
        result = await service.extract_coordinates(
            address="Mount Kilimanjaro",
            city=None,
            country_name="Tanzania",
            country_code=None,
            expected_location_type="feature",
        )
        assert result is not None
        assert result["selected_result_type"] == "massif"
        assert result["lat"] == -3.0674

    run_async_in_thread(_run())
    assert queries == [
        "Mount Kilimanjaro, Tanzania",
        "kilimanjaro, Tanzania",
    ]

###############################################################################
def test_nominatim_rejects_partial_acronym_child_for_named_target() -> None:
    service = NominatimService(user_agent="test-suite", timeout=0.1)

    ranked = service.rank_candidates(
        [
            {
                "lat": "52.2158",
                "lon": "4.4165",
                "display_name": "NCRC Visitor Shop, Noordwijk, Netherlands",
                "class": "shop",
                "type": "gift",
                "importance": 0.8,
                "address": {"town": "Noordwijk", "country": "Netherlands"},
                "namedetails": {"name": "NCRC Visitor Shop"},
            }
        ],
        address="Northern Coastal Research Center facility",
        city="Noordwijk",
        country_name="Netherlands",
        country_code=None,
        query="ncrc, Noordwijk, Netherlands",
        expected_location_type="poi",
    )

    assert ranked == []

###############################################################################
def test_nominatim_keeps_station_candidate_for_transport_qualified_query() -> None:
    service = NominatimService(user_agent="test-suite", timeout=0.1)

    ranked = service.rank_candidates(
        [
            {
                "lat": "46.0049",
                "lon": "8.9468",
                "display_name": "Lugano, Via Paolo Regazzoni, Lugano, Ticino, Switzerland",
                "class": "railway",
                "type": "station",
                "importance": 0.4,
                "address": {"city": "Lugano", "country": "Switzerland"},
                "namedetails": {"name": "Lugano"},
            }
        ],
        address="Lugano railway station",
        city=None,
        country_name=None,
        country_code=None,
        query="Lugano railway station",
        expected_location_type="station",
    )

    assert len(ranked) == 1

###############################################################################
def test_nominatim_asks_for_context_when_query_is_only_a_generic_descriptor() -> None:
    service = NominatimService(user_agent="test-suite", timeout=0.1)
    ranked = [
        {
            "display_name": "Amsterdam Centraal, Amsterdam, Netherlands",
            "lat": 52.378,
            "lon": 4.9,
            "confidence": 0.9,
            "geocoder_importance": 0.8,
            "selected_result_type": "train_station",
            "selected_result_class": "railway",
        },
        {
            "display_name": "Zurich Hauptbahnhof, Zurich, Switzerland",
            "lat": 47.378,
            "lon": 8.54,
            "confidence": 0.5,
            "geocoder_importance": 0.2,
            "selected_result_type": "station",
            "selected_result_class": "railway",
        },
    ]

    result = service._find_ambiguous_candidates(
        ranked, expected_location_type=None, query="central station", has_parent_context=False
    )
    named = service._find_ambiguous_candidates(
        ranked, expected_location_type=None, query="Amsterdam Centraal", has_parent_context=False
    )

    assert len(result) == 2
    assert named == []

###############################################################################
def test_nominatim_district_ranking_rejects_nearby_child_features() -> None:
    service = NominatimService(user_agent="test-suite", timeout=0.1)
    ranked = service.rank_candidates(
        [
            {
                "lat": "41.8338",
                "lon": "12.4709",
                "display_name": "E.U.R., Municipio Roma IX, Rome, Italy",
                "class": "place",
                "type": "suburb",
                "importance": 0.5,
                "address": {"suburb": "E.U.R.", "city": "Rome", "country": "Italy"},
            },
            {
                "lat": "41.8566",
                "lon": "12.4759",
                "display_name": "Centro Primario di distribuzione Roma EUR, Rome, Italy",
                "class": "amenity",
                "type": "post_depot",
                "importance": 0.8,
                "address": {"quarter": "San Paolo", "city": "Rome", "country": "Italy"},
            },
        ],
        address="EUR district",
        city="Rome",
        country_name="Italy",
        country_code=None,
        query="EUR district, Rome, Italy",
        expected_location_type="district",
    )

    assert len(ranked) == 1
    assert ranked[0]["selected_result_type"] == "suburb"

# --- test_location_search_request_schema.py ---



###############################################################################
def _base_payload() -> dict[str, object]:
    return {
        "resolved_location": {
            "label": "Rome, Italy",
            "latitude": 41.9,
            "longitude": 12.5,
            "city": "Rome",
            "country": "Italy",
        },
        "action_id": "air_quality",
        "time_mode": "current",
        "viewport": {
            "center_latitude": 41.9,
            "center_longitude": 12.5,
            "radius_m": 2500.0,
        },
    }

###############################################################################
def test_accepts_canonical_request_fields() -> None:
    request = LocationSearchRequest.model_validate(
        {
            **_base_payload(),
            "basemap_id": "osm_default",
            "overlay_ids": ["openaq_air_quality"],
            "viewport_intent": {
                "scope": "street",
                "tighten_relative_to_active": False,
                "reason": "local_area_request",
            },
            "presentation": {
                "emphasize_overlays": True,
                "high_contrast": False,
                "show_legend": True,
            },
        }
    )
    assert request.basemap_id == "osm_default"
    assert request.overlay_ids == ["openaq_air_quality"]
    assert request.resolved_location.city == "Rome"
    assert request.viewport_intent is not None
    assert request.viewport_intent.scope == "street"

###############################################################################
@pytest.mark.parametrize(
    "removed_field,value",
    [
        ("map_tiles", "OpenStreetMap"),
        ("geospatial_filter", ["air_quality"]),
        ("geospatial_layers", ["air_quality"]),
    ],
)
def test_rejects_removed_request_fields(removed_field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        LocationSearchRequest.model_validate({**_base_payload(), removed_field: value})

###############################################################################
def test_nominatim_does_not_rival_an_exact_city_with_a_longer_name_that_only_lists_it_as_alias() -> None:
    service = NominatimService(user_agent="test-suite", timeout=0.1)
    city = {
        "display_name": "Saint-Étienne, Loire, Auvergne-Rhône-Alpes, France", "lat": 45.43, "lon": 4.39,
        "confidence": 0.82, "geocoder_importance": 0.65,
        "selected_result_type": "administrative", "selected_address_type": "city",
        "address": {"city": "Saint-Étienne", "state": "Auvergne-Rhône-Alpes", "country": "France"},
        "namedetails": {"name": "Saint-Étienne", "name:fr": "Saint-Étienne"},
    }
    village = {
        "display_name": "Saint-Étienne-la-Cigogne, Plaine-d'Argenson, Nouvelle-Aquitaine, France", "lat": 46.2, "lon": -0.4,
        "confidence": 0.8159, "geocoder_importance": 0.52,
        "selected_result_type": "village",
        "address": {"village": "Saint-Étienne-la-Cigogne", "state": "Nouvelle-Aquitaine", "country": "France"},
        "namedetails": {"name": "Saint-Étienne-la-Cigogne", "alt_name": "Saint-Étienne"},
    }

    assert service._find_ambiguous_candidates(
        [city, village], expected_location_type="city", query="Saint-Etienne, France", has_parent_context=True
    ) == []


###############################################################################
def test_nominatim_retries_a_transient_dns_failure_but_not_a_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    from urllib.error import URLError
    import socket

    import server.services.geospatial.nominatim as module

    class _Response:
        def __enter__(self) -> "_Response":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return b"[]"

    def run(failures: list[Exception]) -> int:
        calls: list[int] = []

        def fake_urlopen(*args: object, **kwargs: object) -> _Response:
            calls.append(1)
            if failures:
                raise failures.pop(0)
            return _Response()

        monkeypatch.setattr(module, "urlopen", fake_urlopen)
        monkeypatch.setattr(module.time, "sleep", lambda _s: None)
        service = NominatimService()
        service._min_request_interval_s = 0.0  # pyright: ignore[reportPrivateUsage]
        service.perform_request({"q": f"x{len(calls)}-{id(failures)}"})
        return len(calls)

    assert run([URLError(OSError(11001, "getaddrinfo failed"))]) == 2
    assert run([URLError(socket.timeout("timed out"))]) == 1
