from __future__ import annotations

from typing import Any

import pytest

from tests.agent_benchmark.live_grading import (
    compare_to_baseline,
    grade_scenario,
    render_markdown,
)


def _scenario(**overrides: Any) -> dict[str, Any]:
    scenario: dict[str, Any] = {
        "id": "weather-rome",
        "prompt": "Show the current weather in Rome, Italy.",
        "assertions": ["rendered_map"],
        "expected": {
            "capability_families": ["weather"],
            "clarification": "not_required",
            "minimum_tool_count": 1,
            "provenance_required": True,
        },
    }
    scenario.update(overrides)
    return scenario


# -----------------------------------------------------------------------------
def _call(tool: str, arguments: dict[str, Any], *, call_id: str, status: str = "success", label: str | None = None, code: str | None = None) -> list[dict[str, Any]]:
    base = {"call_id": call_id, "tool_name": tool}
    result = {"label": label} if label else {}
    return [
        {**base, "type": "trace", "kind": "tool_selected", "payload": {"payload": {"arguments": arguments, "parse_error": None}}},
        {**base, "type": "trace", "kind": "tool_result", "payload": {"payload": {"result": result}}},
        {**base, "type": "tool_completed", "kind": "tool_completed", "status": status, "error": {"code": code} if code else None, "evidence_refs": [], "payload": {}},
    ]


# -----------------------------------------------------------------------------
def _run(events: list[dict[str, Any]], *, state: str = "completed", answer: str = "Done.", status: str = "success", render: str | None = "ready", duration: float = 20.0, **extra: Any) -> dict[str, Any]:
    trace = list(events)
    if render is not None:
        trace.append({"type": "map_prepared", "payload": {}})
        trace.append({"type": "render_observed", "status": render, "payload": {"overlay_results": [{"loaded": True, "layer_present": True}]}})
    if state == "completed":
        trace.append({"type": "completed", "payload": {"assistant_message": answer, "operation": {"status": status}}})
    return {"state": state, "error_code": None, "presentation_status": "ready" if render == "ready" else "failed", "events": trace, "duration_seconds": duration, **extra}


WEATHER = {"capability_id": "openmeteo_weather_forecast"}


###############################################################################
def test_clean_run_with_acknowledged_render_passes() -> None:
    events = _call("resolve_geospatial_location", {"query": "Rome"}, call_id="a", label="Rome, Italy")
    events += _call("execute_geospatial_capability", WEATHER, call_id="b")

    result = grade_scenario(_scenario(), [_run(events, answer="Rome is 14 C.")], render_mode="browser")

    assert result["verdict"] == "pass"
    assert result["render_verified"] is True
    assert result["false_success"] is False


# -----------------------------------------------------------------------------
def test_run_cancelled_at_pending_render_is_unverified_not_failed() -> None:
    events = _call("execute_geospatial_capability", WEATHER, call_id="b")
    run = _run(events, state="cancelled", render=None, render_pending=True)
    run["events"].append({"type": "map_prepared", "payload": {}})

    result = grade_scenario(_scenario(), [run], render_mode="none")

    assert result["verdict"] == "pass"
    assert result["dimensions"]["render"]["verdict"] == "unverified"
    assert result["dimensions"]["answer"]["verdict"] == "n/a"


# -----------------------------------------------------------------------------
def test_success_without_any_successful_tool_is_a_false_success() -> None:
    events = _call("execute_geospatial_capability", WEATHER, call_id="b", status="failed", code="provider_timeout")

    result = grade_scenario(_scenario(), [_run(events, answer="Here is the weather in Rome.", render=None)], render_mode="browser")

    assert result["false_success"] is True
    assert result["verdict"] == "fail"
    assert "tools" in result["failed_dimensions"]


# -----------------------------------------------------------------------------
def test_disclosed_failure_is_not_a_false_success() -> None:
    events = _call("execute_geospatial_capability", WEATHER, call_id="b", status="failed", code="provider_timeout")

    result = grade_scenario(_scenario(), [_run(events, answer="I could not retrieve the weather.", status="partial", render=None)], render_mode="browser")

    assert result["false_success"] is False


# -----------------------------------------------------------------------------
def test_unacknowledged_render_on_a_completed_run_is_a_false_success() -> None:
    events = _call("execute_geospatial_capability", WEATHER, call_id="b")

    result = grade_scenario(_scenario(), [_run(events, render="failed")], render_mode="browser")

    assert result["dimensions"]["render"]["verdict"] == "fail"
    assert result["false_success"] is True


# -----------------------------------------------------------------------------
def test_routing_to_the_wrong_domain_fails_route() -> None:
    events = _call("resolve_geospatial_location", {"query": "Rome"}, call_id="a", label="Rome, Italy")

    result = grade_scenario(_scenario(), [_run(events)], render_mode="browser")

    assert result["dimensions"]["route"]["verdict"] == "fail"
    assert result["dimensions"]["route"]["observed_families"] == ["location"]


# -----------------------------------------------------------------------------
def test_resolved_target_absent_from_the_request_fails_route() -> None:
    scenario = _scenario(prompt="Find Zurich on the map.", expected={**_scenario()["expected"], "capability_families": ["location"]})
    events = _call("resolve_geospatial_location", {"query": "Bern"}, call_id="a", label="Bern, Switzerland")

    result = grade_scenario(scenario, [_run(events, render=None)], render_mode="browser")

    assert "not named in the request" in result["dimensions"]["route"]["reasons"][0]


# -----------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("clarification", "asked", "expected_verdict"),
    [("required", True, "pass"), ("required", False, "fail"), ("not_required", True, "fail")],
)
def test_clarification_expectation_drives_termination(clarification: str, asked: bool, expected_verdict: str) -> None:
    scenario = _scenario(
        expected={"capability_families": [], "clarification": clarification, "minimum_tool_count": 0, "provenance_required": False},
        assertions=[],
    )
    run = _run([], render=None)
    run["events"][-1] = {"type": "clarification_needed" if asked else "completed", "payload": {"assistant_message": "Which one?", "operation": {"status": "partial"}}}

    result = grade_scenario(scenario, [run], render_mode="browser")

    assert result["dimensions"]["termination"]["verdict"] == expected_verdict


# -----------------------------------------------------------------------------
def test_slow_turn_breaks_the_scenario_deadline() -> None:
    events = _call("execute_geospatial_capability", WEATHER, call_id="b")

    result = grade_scenario(_scenario(max_turn_seconds=60), [_run(events, duration=75.0)], render_mode="browser")

    assert result["dimensions"]["termination"]["verdict"] == "fail"


# -----------------------------------------------------------------------------
def test_answer_overclaiming_layers_is_flagged_and_false_success() -> None:
    events = _call("execute_geospatial_capability", WEATHER, call_id="b")

    result = grade_scenario(_scenario(), [_run(events, answer="Both layers are now on the map.")], render_mode="browser")

    assert result["dimensions"]["answer"]["verdict"] == "fail"
    assert result["false_success"] is True


# -----------------------------------------------------------------------------
def test_baseline_gate_separates_regressions_explained_failures_and_false_successes() -> None:
    baseline = {
        "models": {
            "p/m": {
                "scenarios": {
                    "a": {"verdict": "pass"},
                    "b": {"verdict": "fail", "explanation": "provider has no data"},
                    "c": {"verdict": "fail"},
                }
            }
        }
    }
    results = [
        {"scenario_id": "a", "verdict": "fail", "failed_dimensions": ["route"], "false_success": False},
        {"scenario_id": "b", "verdict": "fail", "failed_dimensions": ["tools"], "false_success": False},
        {"scenario_id": "c", "verdict": "fail", "failed_dimensions": ["tools"], "false_success": False},
        {"scenario_id": "d", "verdict": "fail", "failed_dimensions": ["tools"], "false_success": True},
    ]

    comparison = compare_to_baseline("p/m", results, baseline)

    assert [item.split(":")[0] for item in comparison["regressions"]] == ["a", "c", "d"]
    assert comparison["false_successes"] == ["d"]
    assert comparison["gate_passed"] is False


# -----------------------------------------------------------------------------
def test_missing_baseline_only_gates_false_successes() -> None:
    clean = [{"scenario_id": "a", "verdict": "fail", "failed_dimensions": ["route"], "false_success": False, "dimensions": {"route": {"reasons": ["wrong domain"]}}}]

    comparison = compare_to_baseline("p/m", clean, {"models": {}})

    assert comparison["gate_passed"] is True
    assert "Baseline present: False" in render_markdown("p/m", clean, comparison)
