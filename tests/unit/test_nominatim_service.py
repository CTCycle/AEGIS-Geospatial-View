from __future__ import annotations

from AEGIS.server.services.geospatial.nominatim import NominatimService


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
    )
    assert ranked
    assert ranked[0]["selected_result_type"] == "attraction"
    assert ranked[0]["lat"] == 41.8902
