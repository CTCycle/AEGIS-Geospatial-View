from __future__ import annotations

from AEGIS.server.domain.extraction.models import ExtractedIntent, ExtractedIntentPatch
from AEGIS.server.domain.extraction.patching import merge_extracted_intent


def test_parser_patch_merge_replaces_non_null_values() -> None:
    base = ExtractedIntent(
        location={"address": "Rome", "city": "Rome", "country": "Italy"},
        coordinates={"latitude": None, "longitude": None},
        filters=["traffic"],
        certainty=0.2,
    )
    patch = ExtractedIntentPatch(
        coordinates={"latitude": 41.9, "longitude": 12.5},
        filters=["weather"],
        certainty=0.8,
    )
    merged = merge_extracted_intent(base, patch)
    assert merged.coordinates.latitude == 41.9
    assert merged.coordinates.longitude == 12.5
    assert merged.filters == ["weather"]
    assert merged.certainty == 0.8
