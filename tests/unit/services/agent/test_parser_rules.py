from __future__ import annotations

from AEGIS.server.services.agent.parser_rules import (
    detect_disallowed_patterns,
    detect_location_signals,
)


def test_detect_location_signals_with_coordinates() -> None:
    signals = detect_location_signals("show map at 41.9028, 12.4964")
    assert signals
    assert signals[0].signal_type == "coordinates"


def test_detect_disallowed_comparative_pattern() -> None:
    patterns = detect_disallowed_patterns("show me the rainiest place in Europe")
    assert patterns
    assert patterns[0].pattern_id == "comparative_superlative"
