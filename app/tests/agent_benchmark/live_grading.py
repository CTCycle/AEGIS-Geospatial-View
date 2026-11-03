"""Trace-level grading of live model runs against the scenario matrix.

The grader consumes the public run trace (``GET /conversations/{id}/runs/{id}/trace``
events plus the run snapshot) and judges the model's *behaviour*: route, tool
sequence, termination, evidence provenance, final-answer consistency and the
render verdict. It never calls a model or a provider, so it is deterministic and
unit-testable against recorded or synthetic traces.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence
from typing import Any

from server.services.agent.final_answer_check import check_final_answer

PASS = "pass"
FAIL = "fail"
NA = "n/a"
UNVERIFIED = "unverified"

DATA_TOOLS = frozenset({"resolve_geospatial_location", "execute_geospatial_capability"})
SUCCESS_STATUSES = frozenset({"success", "valid_empty"})
# Tool failures caused by the model's own call rather than by a provider.
MODEL_INDUCED_ERRORS = frozenset(
    {
        "invalid_arguments",
        "unknown_tool",
        "tool_not_exposed",
        "semantic_validation_failed",
        "stale_map_revision",
        "unknown_layer",
        "invalid_transform",
        "invalid_value_field",
    }
)
MAX_INVALID_CALLS = 3
DEFAULT_MAX_TURN_SECONDS = 180.0
TERMINAL_RENDER_FAILURES = frozenset({"failed", "render_timeout"})
COMPOUND_ASSERTIONS = frozenset({"compound_tasks", "two_capabilities", "poi_and_weather", "append_layer"})
_DISCLOSURE = re.compile(
    r"\b(unavailable|could not|couldn't|unable|missing|only|partial(?:ly)?|no data|"
    r"not (?:available|supported|completed|retrieved)|failed|don't have|do not have|"
    r"cannot|can't|limited)\b",
    re.IGNORECASE,
)

# Capability-id patterns per matrix capability family. ``location`` is matched
# by the resolver tool rather than by a capability id.
FAMILY_PATTERNS: dict[str, re.Pattern[str]] = {
    family: re.compile(pattern, re.IGNORECASE)
    for family, pattern in {
        "weather": r"weather|pressure_humidity|radar|precipitation|imerg|temperature",
        "poi": r"poi|overpass|opentripmap|overture|chargemap|airports|places|amenit",
        "air_quality": r"air_quality|openaq|aerosol|ozone",
        "elevation": r"elevation|srtm|terrain",
        "boundaries": r"boundar|nuts|admin",
        "land_cover": r"land_cover|worldcover|igbp",
        "transit": r"transit|gtfs|station|rail",
        "population": r"population|demograph|acs|census|eurostat",
        "roads": r"road|overpass|traffic|tomtom|street",
        "earthquakes": r"earthquake|seismic|usgs_eq|emsc",
    }.items()
}


###############################################################################
def _text(value: object) -> str:
    return value if isinstance(value, str) else ""


# -----------------------------------------------------------------------------
def _fold(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).casefold()


# -----------------------------------------------------------------------------
def _inner(event: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return the operational payload of an event (trace events nest it twice)."""

    payload = event.get("payload")
    if not isinstance(payload, Mapping):
        return {}
    if event.get("type") == "trace":
        nested = payload.get("payload")  # type: ignore[union-attr]
        return nested if isinstance(nested, Mapping) else {}
    return payload  # type: ignore[return-value]


# -----------------------------------------------------------------------------
def _error_code(event: Mapping[str, Any]) -> str | None:
    error = event.get("error")
    if isinstance(error, Mapping):
        code = error.get("code")  # type: ignore[union-attr]
        return code if isinstance(code, str) else None
    return error if isinstance(error, str) and error else None


# -----------------------------------------------------------------------------
def _capability_ids(tool: str, arguments: Mapping[str, Any]) -> list[str]:
    ids: list[str] = []
    capability = arguments.get("capability_id")
    if isinstance(capability, str):
        ids.append(capability)
    actions = arguments.get("actions")
    if tool == "apply_map_plan" and isinstance(actions, list):
        for action in actions:  # type: ignore[union-attr]
            if isinstance(action, Mapping) and isinstance(action.get("capability_id"), str):
                ids.append(action["capability_id"])  # type: ignore[index]
    return ids


###############################################################################
def extract_tool_calls(events: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Join tool selections, results and completions into one record per call."""

    calls: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for event in events:
        call_id = event.get("call_id")
        tool = event.get("tool_name")
        if not isinstance(call_id, str) or not isinstance(tool, str):
            continue
        record = calls.get(call_id)
        if record is None:
            record = {
                "call_id": call_id,
                "tool": tool,
                "arguments": {},
                "status": None,
                "error_code": None,
                "evidence_refs": [],
                "location": None,
                "parse_error": None,
            }
            calls[call_id] = record
            order.append(call_id)
        kind, inner = event.get("kind"), _inner(event)
        if kind == "tool_selected":
            arguments = inner.get("arguments")
            record["arguments"] = dict(arguments) if isinstance(arguments, Mapping) else {}
            record["parse_error"] = inner.get("parse_error")
        elif kind == "tool_result":
            result = inner.get("result")
            if isinstance(result, Mapping) and isinstance(result.get("label"), str):
                record["location"] = result["label"]  # type: ignore[index]
        elif event.get("type") == "tool_completed":
            record["status"] = event.get("status")
            record["error_code"] = _error_code(event)
            refs = event.get("evidence_refs")
            record["evidence_refs"] = list(refs) if isinstance(refs, list) else []  # type: ignore[arg-type]
    return [calls[call_id] for call_id in order]


# -----------------------------------------------------------------------------
def _families(call: Mapping[str, Any]) -> set[str]:
    tool = call["tool"]
    arguments: Mapping[str, Any] = call["arguments"]
    found: set[str] = set()
    if tool == "resolve_geospatial_location":
        found.add("location")
    for capability in _capability_ids(tool, arguments):
        found.update(name for name, pattern in FAMILY_PATTERNS.items() if pattern.search(capability))
    if tool == "apply_map_plan" and "fit_location" in str(arguments):
        found.add("location")
    return found


# -----------------------------------------------------------------------------
def _unrecovered_failures(calls: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """Failed data calls not followed by a later success of the same tool and capability."""

    unresolved: list[Mapping[str, Any]] = []
    for index, call in enumerate(calls):
        if call["tool"] not in DATA_TOOLS or call["status"] in SUCCESS_STATUSES or call["status"] is None:
            continue
        key = (call["tool"], tuple(_capability_ids(call["tool"], call["arguments"])))
        recovered = any(
            later["status"] in SUCCESS_STATUSES
            and (later["tool"], tuple(_capability_ids(later["tool"], later["arguments"]))) == key
            for later in calls[index + 1 :]
        )
        if not recovered:
            unresolved.append(call)
    return unresolved


###############################################################################
def _final_text(runs: Sequence[Mapping[str, Any]]) -> tuple[str, str | None]:
    """Return the last run's final answer and its terminal event type."""

    events: Sequence[Mapping[str, Any]] = runs[-1]["events"]
    terminal = next(
        (e for e in reversed(events) if e.get("type") in {"completed", "clarification_needed"}), None
    )
    if terminal is not None:
        message = _text(_inner(terminal).get("assistant_message"))
        return message, _text(terminal.get("type"))
    drafted = next((e for e in reversed(events) if e.get("type") == "assistant_text_completed"), None)
    return (_text(_inner(drafted).get("content")) if drafted else ""), None


# -----------------------------------------------------------------------------
def _operation_status(runs: Sequence[Mapping[str, Any]]) -> str | None:
    for event in reversed(runs[-1]["events"]):
        if event.get("type") == "completed":
            operation = _inner(event).get("operation")
            if isinstance(operation, Mapping):
                return _text(operation.get("status")) or None  # type: ignore[union-attr]
    return None


# -----------------------------------------------------------------------------
def _termination_reason(runs: Sequence[Mapping[str, Any]]) -> str:
    last = runs[-1]
    for event in reversed(last["events"]):
        if event.get("kind") == "completion":
            reason = _inner(event).get("completion_reason")
            if isinstance(reason, str):
                return reason
    return _text(last.get("error_code")) or _text(last.get("state")) or "unknown"


# -----------------------------------------------------------------------------
def _dimension(verdict: str, **details: Any) -> dict[str, Any]:
    return {"verdict": verdict, **details}


###############################################################################
def grade_scenario(
    scenario: Mapping[str, Any],
    runs: Sequence[Mapping[str, Any]],
    *,
    render_mode: str,
) -> dict[str, Any]:
    """Grade one scenario execution.

    ``runs`` holds one record per conversation turn with ``state``,
    ``error_code``, ``presentation_status``, ``duration_seconds``, ``timed_out``
    and ``events`` (the public run trace). ``render_mode`` is ``"browser"`` when
    a real browser acknowledged renders or ``"none"`` when it could not.
    """

    expected: Mapping[str, Any] = scenario["expected"]
    prompts = [scenario["prompt"]] if "prompt" in scenario else list(scenario["turns"])
    if not runs:
        return {
            "scenario_id": scenario["id"],
            "verdict": FAIL,
            "false_success": False,
            "dimensions": {"termination": _dimension(FAIL, reason="no_run_recorded")},
        }

    events = [event for run in runs for event in run["events"]]
    calls = extract_tool_calls(events)
    data_calls = [call for call in calls if call["tool"] in DATA_TOOLS]
    successful = [call for call in data_calls if call["status"] in SUCCESS_STATUSES]
    unresolved = _unrecovered_failures(calls)
    last = runs[-1]
    answer, terminal_type = _final_text(runs)
    operation_status = _operation_status(runs)
    clarification = expected["clarification"]
    families_expected = list(expected.get("capability_families", []))
    prompt_blob = _fold(" ".join(prompts))
    dims: dict[str, dict[str, Any]] = {}

    # Termination -------------------------------------------------------------
    deadline = float(scenario.get("max_turn_seconds") or DEFAULT_MAX_TURN_SECONDS)
    slowest = max((float(run.get("duration_seconds") or 0) for run in runs), default=0.0)
    asked = terminal_type == "clarification_needed"
    reasons: list[str] = []
    if any(run.get("timed_out") for run in runs) or slowest > deadline:
        reasons.append(f"exceeded {deadline:.0f}s turn deadline")
    if not asked and last["state"] != "completed" and not (
        render_mode == "none" and last.get("render_pending")
    ):
        reasons.append(f"run ended {last['state']} ({_text(last.get('error_code')) or 'no error code'})")
    if clarification == "required" and not asked:
        reasons.append("clarification required but not requested")
    if clarification == "not_required" and asked:
        reasons.append("unnecessary clarification")
    dims["termination"] = _dimension(
        FAIL if reasons else PASS,
        reasons=reasons,
        termination_reason=_termination_reason(runs),
        slowest_turn_seconds=round(slowest, 1),
    )

    # Route: domain families and targets --------------------------------------
    observed = set().union(*[_families(call) for call in data_calls]) if data_calls else set()
    route_reasons: list[str] = []
    if families_expected:
        needed_all = len(families_expected) >= 2 and int(expected["minimum_tool_count"]) >= 2 or bool(
            COMPOUND_ASSERTIONS & set(scenario.get("assertions", []))
        )
        hits = [family for family in families_expected if family in observed]
        if (needed_all and len(hits) < len(families_expected)) or (not needed_all and not hits):
            route_reasons.append(f"expected {families_expected}, routed {sorted(observed)}")
    off_target = [
        call["location"]
        for call in successful
        if call["tool"] == "resolve_geospatial_location"
        and call["location"]
        and not any(
            _fold(segment.strip()) in prompt_blob
            for segment in [call["location"], *str(call["location"]).split(",")]
            if segment.strip()
        )
        and not (isinstance(call["arguments"].get("query"), str) and _fold(call["arguments"]["query"]) in prompt_blob)
        and not re.search(r"-?\d+\.\d+", prompt_blob)
    ]
    if off_target:
        route_reasons.append(f"resolved targets not named in the request: {off_target}")
    dims["route"] = _dimension(
        FAIL if route_reasons else (PASS if families_expected else NA),
        reasons=route_reasons,
        expected_families=families_expected,
        observed_families=sorted(observed),
    )

    # Tool sequence validity --------------------------------------------------
    invalid = [
        call
        for call in calls
        if call["parse_error"] or call["error_code"] in MODEL_INDUCED_ERRORS
    ]
    tool_reasons: list[str] = []
    minimum = int(expected["minimum_tool_count"])
    if len(successful) < minimum and not asked:
        tool_reasons.append(f"{len(successful)} successful data calls, expected at least {minimum}")
    if len(invalid) > MAX_INVALID_CALLS:
        tool_reasons.append(f"{len(invalid)} model-induced invalid calls (limit {MAX_INVALID_CALLS})")
    signatures = [(c["tool"], repr(sorted(c["arguments"].items()))) for c in successful]
    if any(signatures.count(sig) > 1 for sig in signatures) and "no_duplicate_layer_call" in scenario.get(
        "assertions", []
    ):
        tool_reasons.append("duplicate identical successful call")
    dims["tools"] = _dimension(
        FAIL if tool_reasons else PASS,
        reasons=tool_reasons,
        sequence=[f"{c['tool']}:{c['status']}" for c in calls],
        invalid_calls=len(invalid),
    )

    # Evidence provenance -----------------------------------------------------
    provenance_reasons: list[str] = []
    if expected["provenance_required"] and minimum > 0 and not asked:
        if not successful:
            provenance_reasons.append("no successful tool result backs the answer")
    dims["provenance"] = _dimension(
        FAIL if provenance_reasons else (PASS if expected["provenance_required"] else NA),
        reasons=provenance_reasons,
        evidence_refs=sum(len(c["evidence_refs"]) for c in successful),
    )

    # Render verdict ----------------------------------------------------------
    map_prepared = any(e.get("type") == "map_prepared" for e in events)
    observations = [e for e in events if e.get("type") == "render_observed"]
    needs_map = "rendered_map" in scenario.get("assertions", [])
    if not map_prepared:
        render = _dimension(FAIL, reasons=["no map was prepared"]) if needs_map and not asked else _dimension(NA)
    elif render_mode == "none":
        render = _dimension(UNVERIFIED, reasons=["no browser acknowledged the render"])
    elif observations and _text(observations[-1].get("status")) == "ready" and last.get(
        "presentation_status"
    ) not in TERMINAL_RENDER_FAILURES:
        render = _dimension(PASS, attempts=len(observations))
    else:
        render = _dimension(
            FAIL,
            reasons=[f"presentation {_text(last.get('presentation_status')) or 'unacknowledged'}"],
            attempts=len(observations),
        )
    dims["render"] = render

    # Final-answer consistency ------------------------------------------------
    final_answer_available = bool(answer) and (terminal_type is not None)
    answer_violations: list[str] = []
    answer_reasons: list[str] = []
    if not final_answer_available:
        dims["answer"] = _dimension(NA, reasons=["no final answer was produced in this mode"])
    else:
        targets = [call["location"] for call in successful if call["location"]]
        overlays = [r for o in observations[-1:] for r in o.get("payload", {}).get("overlay_results", [])]
        layer_count = (
            sum(1 for r in overlays if r.get("loaded") and r.get("layer_present"))
            if render["verdict"] == PASS
            else None
        )
        unmet = [f"{c['tool']}:{c['error_code'] or c['status']}" for c in unresolved]
        answer_violations = check_final_answer(
            answer,
            target_names=[_text(t) for t in targets],
            layer_count=layer_count,
            unmet=unmet,
        )
        answer_reasons = list(answer_violations)
        dims["answer"] = _dimension(FAIL if answer_reasons else PASS, reasons=answer_reasons)

    # False success -----------------------------------------------------------
    false_reasons: list[str] = []
    completed = last["state"] == "completed" and not asked
    if (
        completed
        and minimum > 0
        and not successful
        and operation_status == "success"
        and not _DISCLOSURE.search(answer)
    ):
        false_reasons.append("completed successfully with no successful data call")
    if last["state"] == "completed" and render["verdict"] == FAIL and map_prepared:
        false_reasons.append("completed although the render was not acknowledged")
    false_reasons.extend(f"answer: {violation}" for violation in answer_violations)
    dims["false_success"] = _dimension(FAIL if false_reasons else PASS, reasons=false_reasons)

    failed = [name for name, dim in dims.items() if dim["verdict"] == FAIL]
    return {
        "scenario_id": scenario["id"],
        "verdict": FAIL if failed else PASS,
        "failed_dimensions": failed,
        "false_success": bool(false_reasons),
        "render_verified": render["verdict"] == PASS,
        "metrics": {
            "data_calls": len(data_calls),
            "successful_data_calls": len(successful),
            "invalid_calls": len(invalid),
            "turns": len(runs),
        },
        "dimensions": dims,
        "final_answer": answer[:1500],
    }


###############################################################################
def compare_to_baseline(
    model_key: str,
    results: Sequence[Mapping[str, Any]],
    baseline: Mapping[str, Any],
) -> dict[str, Any]:
    """Compare graded results with the stored per-model baseline.

    A baseline scenario entry is ``{"verdict": "pass"}`` or
    ``{"verdict": "fail", "explanation": "<known cause>"}``. A scenario that
    fails without a ``pass`` baseline or a documented explanation is a
    regression; any false success fails the gate regardless of the baseline.
    """

    model_baseline = baseline.get("models", {}).get(model_key)
    regressions: list[str] = []
    improvements: list[str] = []
    for result in results:
        entry = (model_baseline or {}).get("scenarios", {}).get(result["scenario_id"])
        failed = result["verdict"] == FAIL
        if entry is None:
            if failed and model_baseline is not None:
                regressions.append(f"{result['scenario_id']}: failed and is not in the baseline")
            continue
        if failed and entry["verdict"] == PASS:
            regressions.append(
                f"{result['scenario_id']}: regressed ({', '.join(result.get('failed_dimensions', []))})"
            )
        elif failed and not entry.get("explanation"):
            regressions.append(f"{result['scenario_id']}: fails without a documented explanation")
        elif not failed and entry["verdict"] == FAIL:
            improvements.append(result["scenario_id"])
    false_successes = [r["scenario_id"] for r in results if r["false_success"]]
    return {
        "model": model_key,
        "baseline_present": model_baseline is not None,
        "regressions": regressions,
        "improvements": improvements,
        "false_successes": false_successes,
        "gate_passed": not regressions and not false_successes,
    }


###############################################################################
def render_markdown(model_key: str, results: Sequence[Mapping[str, Any]], comparison: Mapping[str, Any]) -> str:
    """Render the per-model summary."""

    passed = sum(1 for r in results if r["verdict"] == PASS)
    unverified = sum(1 for r in results if r["dimensions"].get("render", {}).get("verdict") == UNVERIFIED)
    lines = [
        f"# Live evaluation: {model_key}",
        "",
        f"- Scenarios: {len(results)}, passed: {passed}, failed: {len(results) - passed}",
        f"- False successes: {len(comparison['false_successes'])}",
        f"- Render unverified (no browser): {unverified}",
        f"- Baseline present: {comparison['baseline_present']}",
        f"- Gate: {'PASS' if comparison['gate_passed'] else 'FAIL'}",
        "",
        "| Scenario | Verdict | Failed dimensions | Render | False success |",
        "|---|---|---|---|---|",
    ]
    for result in results:
        lines.append(
            f"| {result['scenario_id']} | {result['verdict']} | "
            f"{', '.join(result.get('failed_dimensions', [])) or '-'} | "
            f"{result['dimensions'].get('render', {}).get('verdict', '-')} | "
            f"{'YES' if result['false_success'] else 'no'} |"
        )
    for title, key in (("Regressions", "regressions"), ("False successes", "false_successes")):
        if comparison[key]:
            lines += ["", f"## {title}", *[f"- {item}" for item in comparison[key]]]
    failures = [r for r in results if r["verdict"] == FAIL]
    if failures:
        lines += ["", "## Failure details"]
        for result in failures:
            for name in result.get("failed_dimensions", []):
                reasons = "; ".join(result["dimensions"][name].get("reasons", []))
                lines.append(f"- `{result['scenario_id']}` {name}: {reasons}")
    return "\n".join(lines) + "\n"
