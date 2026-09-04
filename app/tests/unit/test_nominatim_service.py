from __future__ import annotations

from datetime import UTC, datetime

from tests.conftest import run_async_in_thread

from server.services.geospatial.nominatim import NominatimService


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
