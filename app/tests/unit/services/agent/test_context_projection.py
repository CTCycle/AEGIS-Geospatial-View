from __future__ import annotations

import json

from server.domain.agent.decision import ResolvedLocation
from server.prompts.agent import NATIVE_CONTEXT_PREFIX, build_native_context_messages
from server.services.geospatial.map_session_builder import location_frame_points
from server.services.llm.context_budget import estimate_input_sections


###############################################################################
def _context(summary: dict[str, object]) -> list[dict[str, object]]:
    return build_native_context_messages(
        current_user_message="Now compare precipitation.",
        recent_messages=[],
        active_directives=[],
        task_state={},
        map_memory={},
        summary=None,
        relevant_tool_outcomes=[{"evidence_id": "e1", "summary": summary}],
    )


###############################################################################
def test_an_earlier_series_is_sent_once_per_column_with_every_value() -> None:
    rows = [{"time": f"T{i}", "temperature_2m": i + 0.5} for i in range(24)]
    long_series = str(_context({"hourly_forecast": rows})[-2]["content"])

    assert '"columns":["time","temperature_2m"]' in long_series
    assert long_series.count("temperature_2m") == 1
    assert all(f"{i + 0.5}" in long_series for i in range(24))

    short = str(_context({"hourly_forecast": rows[:2]})[-2]["content"])
    assert json.dumps(rows[:2], separators=(",", ":")) in short


###############################################################################
def test_input_sections_separate_instructions_state_history_and_tools() -> None:
    messages = [
        {"role": "system", "content": "rules"},
        {"role": "user", "content": "earlier"},
        {"role": "system", "content": f"{NATIVE_CONTEXT_PREFIX} {'x' * 400}"},
        {"role": "assistant", "content": None, "tool_calls": [{"id": "1"}]},
        {"role": "tool", "tool_call_id": "1", "content": "y" * 800},
    ]

    sections = estimate_input_sections(messages, working_state_prefix=NATIVE_CONTEXT_PREFIX)

    assert sections["working_state"] > 100
    assert sections["tool_exchanges"] > 200
    assert 0 < sections["system"] < 20
    assert 0 < sections["conversation"] < 20


###############################################################################
def test_a_country_is_framed_by_its_extent_and_a_city_by_its_centre() -> None:
    area = ResolvedLocation(
        label="Italy", latitude=42.8, longitude=12.8, location_type="region", bbox=[6.6, 35.5, 18.5, 47.1]
    )
    city = ResolvedLocation(
        label="Milan", latitude=45.46, longitude=9.19, location_type="city", bbox=[9.0, 45.3, 9.3, 45.6]
    )

    assert location_frame_points(area) == [(6.6, 35.5), (18.5, 47.1)]
    assert location_frame_points(city) == [(9.19, 45.46)]
