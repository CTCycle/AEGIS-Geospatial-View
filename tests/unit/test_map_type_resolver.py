from __future__ import annotations

from AEGIS.server.services.search.map_type_resolver import MapTypeResolver


def test_map_type_resolver_lexical_satellite() -> None:
    resolved = MapTypeResolver().resolve(
        intent={"map_preferences": {"map_type": "auto", "map_type_confidence": 0.1}},
        user_text="I want realistic photographic scenery around Naples",
    )
    assert resolved.map_type == "satellite"
    assert resolved.source == "heuristic"
