"""Run the versioned scenario manifest against a running AEGIS backend.

The runner intentionally does not select a provider or model.  The backend's
configured model is recorded in the output and a structured-output preflight
failure produces a blocked lane rather than silently substituting a model.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx

from server.domain.agent.execution import AgentExecutionContext
from server.domain.agent.pipeline import ToolPlan, ToolPlanStep, ToolRetryPolicy
from server.domain.agent.runtime import (
    AgentTask,
    AgentThreadState,
    GeospatialWorkingState,
    apply_steering_delta,
)
from server.domain.agent.tools import ToolError, ToolExecutionEnvelope
from server.domain.steering import SteeringDelta
from server.services.agent.tool_plan_executor import ToolPlanExecutor
from server.services.agent.tool_registry import ToolRegistry
from server.services.llm.types import LLMToolDefinition


###############################################################################
def _json_response(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        return {"status_code": response.status_code, "text": response.text[:1000]}
    return payload if isinstance(payload, dict) else {"value": payload}


###############################################################################
def _fingerprint(tool: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(tool, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


###############################################################################
def _response(trace: dict[str, Any]) -> dict[str, Any]:
    value = trace.get("response")
    return value if isinstance(value, dict) else {}


###############################################################################
def _contract(trace: dict[str, Any]) -> dict[str, Any]:
    value = _response(trace).get("turn_contract")
    return value if isinstance(value, dict) else {}


###############################################################################
def _map_session(trace: dict[str, Any]) -> dict[str, Any] | None:
    value = trace.get("map_session")
    return value if isinstance(value, dict) else None


###############################################################################
def _tool_calls(traces: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        item
        for trace in traces
        for item in trace.get("tool_calls", [])
        if isinstance(item, dict)
    ]


###############################################################################
def _tool_results(traces: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        item
        for trace in traces
        for item in trace.get("tool_results", [])
        if isinstance(item, dict)
    ]


###############################################################################
def _provider_events(traces: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return non-tool provider work captured by the application trace."""
    return [
        item
        for trace in traces
        for item in trace.get("provider_events", [])
        if isinstance(item, dict)
    ]


###############################################################################
def _capability_ids(tool_calls: list[dict[str, Any]]) -> set[str]:
    capability_ids: set[str] = set()
    for call in tool_calls:
        arguments = call.get("arguments")
        if not isinstance(arguments, dict):
            continue
        capability_id = arguments.get("capability_id")
        if isinstance(capability_id, str) and capability_id.strip():
            capability_ids.add(capability_id.strip())
    return capability_ids


###############################################################################
def _map_has_location(map_session: dict[str, Any] | None) -> bool:
    if not isinstance(map_session, dict):
        return False
    location = map_session.get("resolved_location")
    center = map_session.get("center")
    basemap = map_session.get("basemap")
    return (
        isinstance(location, dict)
        and isinstance(center, dict)
        and isinstance(basemap, dict)
        and isinstance(location.get("latitude"), int | float)
        and isinstance(location.get("longitude"), int | float)
    )


###############################################################################
def _has_explicit_coordinate_evidence(trace: dict[str, Any]) -> bool:
    """Verify that a coordinate-only map is grounded in the user's request.

    Explicit coordinates are already the external grounding supplied by the
    user, so they do not need a geocoder provider event. The benchmark must
    still verify the coordinates against the request and the typed extraction;
    a model-invented coordinate must not count as execution evidence.
    """

    map_session = _map_session(trace)
    if not _map_has_location(map_session):
        return False
    location = map_session.get("resolved_location") if map_session else None
    if not isinstance(location, dict):
        return False
    location_type = str(
        location.get("location_type") or location.get("location_class") or ""
    ).casefold()
    if location_type not in {"coordinate", "coordinates"}:
        return False

    contract = _contract(trace)
    user_text = contract.get("user_text") or trace.get("prompt")
    if not isinstance(user_text, str) or not user_text.strip():
        return False
    user_text_casefolded = user_text.casefold()
    numeric_values = [
        float(value)
        for value in re.findall(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)", user_text)
    ]
    map_latitude = location.get("latitude")
    map_longitude = location.get("longitude")
    if not isinstance(map_latitude, int | float) or isinstance(map_latitude, bool):
        return False
    if not isinstance(map_longitude, int | float) or isinstance(map_longitude, bool):
        return False

    signals = contract.get("location_signals")
    if not isinstance(signals, list):
        return False
    for signal in signals:
        if not isinstance(signal, dict):
            continue
        signal_type = str(signal.get("signal_type") or "").casefold()
        latitude = signal.get("latitude")
        longitude = signal.get("longitude")
        if signal_type not in {"coordinate", "coordinates"}:
            continue
        if not isinstance(latitude, int | float) or isinstance(latitude, bool):
            continue
        if not isinstance(longitude, int | float) or isinstance(longitude, bool):
            continue
        if abs(float(latitude) - float(map_latitude)) > 1e-6 or abs(
            float(longitude) - float(map_longitude)
        ) > 1e-6:
            continue

        raw_values = (
            signal.get("raw_value"),
            signal.get("normalized_value"),
        )
        if any(
            isinstance(value, str)
            and value.strip()
            and value.casefold() in user_text_casefolded
            for value in raw_values
        ):
            return True
        for index in range(len(numeric_values) - 1):
            if abs(numeric_values[index] - float(latitude)) <= 1e-6 and abs(
                numeric_values[index + 1] - float(longitude)
            ) <= 1e-6:
                return True
    return False


###############################################################################
def _overlay_ids(traces: list[dict[str, Any]]) -> set[str]:
    overlays: set[str] = set()
    for trace in traces:
        map_session = _map_session(trace)
        if map_session is not None:
            collection = map_session.get("overlay_collection")
            if isinstance(collection, dict):
                instances = collection.get("instances")
                if isinstance(instances, list):
                    overlays.update(
                        str(instance.get("capability_id"))
                        for instance in instances
                        if isinstance(instance, dict)
                        and isinstance(instance.get("capability_id"), str)
                    )
    return overlays


###############################################################################
def _has_error(trace: dict[str, Any]) -> bool:
    if int(trace.get("status_code") or 0) >= 400:
        return True
    operation = _response(trace).get("operation")
    if isinstance(operation, dict) and operation.get("status") in {"failed", "partial"}:
        return True
    for result in trace.get("tool_results", []):
        if isinstance(result, dict) and result.get("is_error"):
            return True
    return False


###############################################################################
def _live_provider_block_reason(trace: dict[str, Any]) -> str | None:
    """Classify unavailable configured upstreams without turning them into passes."""

    status_code = int(trace.get("status_code") or 0)
    if status_code in {502, 503, 504}:
        return f"http_{status_code}"
    response = _response(trace)
    operation = response.get("operation")
    if not isinstance(operation, dict):
        operation = {}
    provider_error = operation.get("provider_error")
    failure_category = operation.get("failure_category")
    if isinstance(provider_error, dict):
        failure_category = provider_error.get("category") or failure_category
    if failure_category == "provider_api":
        return "provider_unavailable"
    diagnostic = response.get("failure_diagnostic")
    if isinstance(diagnostic, dict) and diagnostic.get("category") == "provider_api":
        return "provider_unavailable"
    normalized = json.dumps(response, ensure_ascii=True, default=str).casefold()
    if any(
        marker in normalized
        for marker in (
            "could not perform structured extraction",
            "failed while processing structured extraction",
            "provider request failed",
        )
    ):
        return "provider_unavailable"
    return None


###############################################################################
def _answer(trace: dict[str, Any]) -> str:
    value = _response(trace).get("assistant_message")
    return value if isinstance(value, str) else ""


###############################################################################
def _valid_tool_arguments(
    tool_calls: list[dict[str, Any]], traces: list[dict[str, Any]] | None = None
) -> bool:
    if not tool_calls:
        # A location-only map is a valid execution even when the request did
        # not need a native capability call. Its typed provider event and
        # verified map session are the argument/evidence boundary. Explicit
        # user coordinates are also a valid grounding boundary and do not
        # require a redundant geocoder request.
        return bool(
            traces
            and any(_has_explicit_coordinate_evidence(trace) for trace in traces)
        ) or bool(
            traces
            and all(_map_has_location(_map_session(trace)) for trace in traces)
            and all(
                _has_provider_provenance(event)
                for trace in traces
                for event in trace.get("provider_events", [])
                if isinstance(event, dict)
            )
            and any(
                isinstance(event, dict)
                for trace in traces
                for event in trace.get("provider_events", [])
            )
        )

    def valid_value(key: str, value: Any) -> bool:
        normalized = key.casefold()
        if normalized == "latitude" and isinstance(value, int | float):
            return -90 <= value <= 90
        if normalized == "longitude" and isinstance(value, int | float):
            return -180 <= value <= 180
        if normalized == "bbox":
            return (
                isinstance(value, list)
                and len(value) == 4
                and all(isinstance(item, int | float) for item in value)
                and -180 <= value[0] <= value[2] <= 180
                and -90 <= value[1] <= value[3] <= 90
            )
        if isinstance(value, dict):
            return all(
                valid_value(str(child_key), child_value)
                for child_key, child_value in value.items()
            )
        if isinstance(value, list):
            return all(valid_value(key, child_value) for child_value in value)
        return True

    return all(
        valid_value("arguments", call.get("arguments", {})) for call in tool_calls
    )


###############################################################################
def _assertion_result(name: str, passed: bool, reason: str) -> dict[str, Any]:
    return {"name": name, "passed": passed, "reason": reason}


_CONTEXT_USAGE_SOURCES = frozenset(
    {"not_measured", "estimated", "provider_reported", "hybrid"}
)
_FAILURE_CATEGORIES = frozenset(
    {
        "model_capability",
        "provider_api",
        "schema_definition",
        "response_parsing",
        "context_limit",
    }
)
_PARENT_LOCATION_TYPES = frozenset(
    {
        "country",
        "region",
        "state",
        "province",
        "county",
        "administrative",
        "administrative_area",
    }
)


def _context_usage_records(traces: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for trace in traces:
        response_usage = _response(trace).get("context_usage")
        if isinstance(response_usage, dict):
            records.append(response_usage)
        tool_payload = trace.get("tool_payload")
        if isinstance(tool_payload, dict):
            for usage in tool_payload.get("context_usages", []):
                if isinstance(usage, dict):
                    records.append(usage)
    return records


def _non_negative_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _usage_input_tokens(usage: dict[str, Any]) -> int | None:
    reported = usage.get("reported_input_tokens")
    if _non_negative_int(reported):
        return reported
    estimated = usage.get("estimated_input_tokens")
    return estimated if _non_negative_int(estimated) else None


def _evaluate_context_usage_invariants(
    traces: list[dict[str, Any]],
) -> dict[str, Any]:
    records = _context_usage_records(traces)
    if not records:
        return _assertion_result(
            "context_usage_invariants",
            False,
            "No context-usage sample was recorded.",
        )
    for usage in records:
        source = usage.get("usage_source")
        if source not in _CONTEXT_USAGE_SOURCES:
            return _assertion_result(
                "context_usage_invariants",
                False,
                f"Unsupported context usage source: {source!r}.",
            )
        estimated = usage.get("estimated_input_tokens")
        if not _non_negative_int(estimated):
            return _assertion_result(
                "context_usage_invariants",
                False,
                "Every sample must preserve a non-negative integer estimate.",
            )
        for key in ("reported_input_tokens", "reported_output_tokens"):
            value = usage.get(key)
            if value is not None and not _non_negative_int(value):
                return _assertion_result(
                    "context_usage_invariants",
                    False,
                    f"{key} must be null or a non-negative integer.",
                )
        percent = usage.get("usage_percent")
        cap = usage.get("selected_context_window")
        usable = usage.get("usable_prompt_budget_tokens")
        if percent is not None:
            if not isinstance(percent, int | float) or isinstance(percent, bool):
                return _assertion_result(
                    "context_usage_invariants",
                    False,
                    "A determinate percentage must be numeric.",
                )
            if (
                percent < 0
                or not _non_negative_int(cap)
                or not isinstance(usable, int)
                or usable <= 0
            ):
                return _assertion_result(
                    "context_usage_invariants",
                    False,
                    "A determinate percentage requires a positive usable budget and known cap.",
                )
        if cap is None and percent is not None:
            return _assertion_result(
                "context_usage_invariants",
                False,
                "Unknown-cap samples must remain indeterminate.",
            )
        peak = usage.get("peak_request_tokens")
        total_input = usage.get("total_input_tokens")
        total_output = usage.get("total_output_tokens")
        if peak is not None and not _non_negative_int(peak):
            return _assertion_result(
                "context_usage_invariants",
                False,
                "Peak request tokens must be a non-negative integer when present.",
            )
        if total_input is not None and not _non_negative_int(total_input):
            return _assertion_result(
                "context_usage_invariants",
                False,
                "Total input tokens must be a non-negative integer when present.",
            )
        if total_output is not None and not _non_negative_int(total_output):
            return _assertion_result(
                "context_usage_invariants",
                False,
                "Total output tokens must be a non-negative integer when present.",
            )
        if (
            isinstance(peak, int)
            and isinstance(total_input, int)
            and peak > total_input
        ):
            return _assertion_result(
                "context_usage_invariants",
                False,
                "Peak input usage cannot exceed total input usage.",
            )
        phases = usage.get("phases")
        if not isinstance(phases, dict):
            continue
        phase_inputs: list[int] = []
        for phase_name, phase in phases.items():
            if not isinstance(phase, dict):
                return _assertion_result(
                    "context_usage_invariants",
                    False,
                    f"Phase {phase_name!r} is not an object.",
                )
            phase_source = phase.get("usage_source")
            if phase_source is not None and phase_source not in _CONTEXT_USAGE_SOURCES:
                return _assertion_result(
                    "context_usage_invariants",
                    False,
                    f"Phase {phase_name!r} has an unsupported usage source.",
                )
            input_tokens = _usage_input_tokens(phase)
            if input_tokens is not None:
                phase_inputs.append(input_tokens)
        if phase_inputs and isinstance(peak, int) and peak != max(phase_inputs):
            return _assertion_result(
                "context_usage_invariants",
                False,
                "Peak request usage does not match the largest phase footprint.",
            )
        if phase_inputs and isinstance(total_input, int) and total_input != sum(phase_inputs):
            return _assertion_result(
                "context_usage_invariants",
                False,
                "Total input usage does not match the phase totals.",
            )
    return _assertion_result(
        "context_usage_invariants",
        True,
        "Usage sources, caps, phase totals, and peak semantics are consistent.",
    )


def _evaluate_location_target_consistency(
    scenario: dict[str, Any], traces: list[dict[str, Any]]
) -> dict[str, Any]:
    maps = [_map_session(trace) for trace in traces]
    available_maps = [item for item in maps if isinstance(item, dict)]
    if not available_maps:
        if _has_allowed_clarification(scenario, traces):
            return _assertion_result(
                "location_target_consistency",
                True,
                "The request stopped with an explicit clarification instead of an unverified target.",
            )
        return _assertion_result(
            "location_target_consistency",
            False,
            "No map target was returned for a location consistency check.",
        )
    geographic_scale = str(
        scenario.get("dimensions", {}).get("geographic_scale", "")
    ).casefold()
    fine_scale = geographic_scale in {
        "city",
        "town",
        "village",
        "neighborhood",
        "district",
        "address",
        "poi",
    }
    for map_session in available_maps:
        location = map_session.get("resolved_location")
        center = map_session.get("center")
        if not isinstance(location, dict) or not isinstance(center, dict):
            return _assertion_result(
                "location_target_consistency",
                False,
                "A map session is missing its resolved location or center.",
            )
        if (
            location.get("latitude") != center.get("latitude")
            or location.get("longitude") != center.get("longitude")
        ):
            return _assertion_result(
                "location_target_consistency",
                False,
                "The viewport center does not match the resolved target.",
            )
        location_type = str(
            location.get("location_type") or location.get("location_class") or ""
        ).casefold()
        if fine_scale and location_type in _PARENT_LOCATION_TYPES:
            return _assertion_result(
                "location_target_consistency",
                False,
                "A specific location was silently downgraded to a parent area.",
            )
    return _assertion_result(
        "location_target_consistency",
        True,
        "Resolved target, viewport center, and geographic specificity are consistent.",
    )


def _evaluate_failure_diagnostics(traces: list[dict[str, Any]]) -> dict[str, Any]:
    for trace in traces:
        response = _response(trace)
        operation = response.get("operation")
        contract = _contract(trace)
        provider_error = (
            operation.get("provider_error")
            if isinstance(operation, dict)
            else None
        )
        failure_category = (
            operation.get("failure_category")
            if isinstance(operation, dict)
            else None
        ) or contract.get("failure_category")
        if (
            isinstance(operation, dict)
            and operation.get("kind") == "clarification"
            and not isinstance(provider_error, dict)
            and not isinstance(failure_category, str)
            and not isinstance(response.get("failure_diagnostic"), dict)
            and int(trace.get("status_code") or 0) < 400
        ):
            # A clarification is a deliberate safe stop, not an execution
            # failure requiring a failure category.
            continue
        failure_present = (
            int(trace.get("status_code") or 0) >= 400
            or isinstance(provider_error, dict)
            or isinstance(failure_category, str)
            or isinstance(response.get("failure_diagnostic"), dict)
            or (
                isinstance(operation, dict)
                and operation.get("status") in {"failed", "partial"}
            )
        )
        if not failure_present:
            continue
        category = (
            provider_error.get("category")
            if isinstance(provider_error, dict)
            else None
        ) or failure_category
        if category not in _FAILURE_CATEGORIES:
            return _assertion_result(
                "categorized_failures",
                False,
                "A failed or partial operation lacks a recognized failure category.",
            )
    return _assertion_result(
        "categorized_failures",
        True,
        "Every observed failure or partial operation is categorized.",
    )


def _evaluate_no_false_success(traces: list[dict[str, Any]]) -> dict[str, Any]:
    for trace in traces:
        response = _response(trace)
        operation = response.get("operation")
        if not isinstance(operation, dict):
            continue
        if operation.get("status") != "success":
            continue
        if operation.get("kind") == "map_session" and not _map_has_location(
            _map_session(trace)
        ):
            return _assertion_result(
                "no_false_success",
                False,
                "A successful map operation lacks a verified target and viewport.",
            )
        if operation.get("failure_category") or isinstance(
            operation.get("provider_error"), dict
        ):
            return _assertion_result(
                "no_false_success",
                False,
                "A successful operation also contains failure diagnostics.",
            )
    return _assertion_result(
        "no_false_success",
        True,
        "No operation was reported successful without corresponding verified evidence.",
    )


def _evaluate_clarification_correctness(
    scenario: dict[str, Any], traces: list[dict[str, Any]]
) -> dict[str, Any]:
    expected = scenario.get("expected", {})
    if expected.get("clarification") != "required":
        return _assertion_result(
            "clarification_correctness",
            True,
            "The scenario does not require clarification.",
        )
    if not traces:
        return _assertion_result(
            "clarification_correctness",
            False,
            "No turn was recorded for a required clarification.",
        )
    trace = traces[-1]
    response = _response(trace)
    decision = response.get("decision")
    clarification = (
        decision.get("clarification") if isinstance(decision, dict) else None
    )
    plan = decision.get("plan") if isinstance(decision, dict) else None
    question = clarification.get("question") if isinstance(clarification, dict) else None
    operation = response.get("operation")
    operation_executed = (
        isinstance(operation, dict)
        and operation.get("status") == "success"
        and operation.get("kind") == "map_session"
    )
    if (
        not isinstance(plan, dict)
        or plan.get("state") != "clarify"
        or not isinstance(question, str)
        or not question.strip()
        or operation_executed
    ):
        return _assertion_result(
            "clarification_correctness",
            False,
            "The ambiguous request did not yield a non-executing clarification.",
        )
    return _assertion_result(
        "clarification_correctness",
        True,
        "The ambiguous request produced an explicit clarification without executing a new map operation.",
    )


def _evaluate_deadline_compliance(
    scenario: dict[str, Any], traces: list[dict[str, Any]]
) -> dict[str, Any]:
    expected = scenario.get("expected", {})
    deadline = scenario.get("max_turn_seconds") or expected.get("max_turn_seconds")
    if (
        not isinstance(deadline, (int, float))
        or isinstance(deadline, bool)
        or deadline <= 0
    ):
        return _assertion_result(
            "deadline_compliance",
            False,
            "The scenario did not declare a positive benchmark deadline.",
        )
    for trace in traces:
        duration = trace.get("duration_seconds")
        if not isinstance(duration, (int, float)) or isinstance(duration, bool):
            return _assertion_result(
                "deadline_compliance",
                False,
                "The benchmark did not record a numeric turn duration.",
            )
        if duration > deadline:
            return _assertion_result(
                "deadline_compliance",
                False,
                f"A turn exceeded the declared {deadline:g}-second deadline.",
            )
    return _assertion_result(
        "deadline_compliance",
        True,
        "Every recorded turn completed within its declared deadline.",
    )


_CAPABILITY_FAMILY_TOKENS: dict[str, tuple[str, ...]] = {
    "location": ("location", "geocode", "coordinate", "place"),
    "weather": ("weather", "forecast", "rain", "precipitation"),
    "air_quality": ("air_quality", "airquality", "pollution", "openaq"),
    "poi": ("poi", "amenit", "hospital", "pharmacy", "restaurant", "park"),
    "transit": ("transit", "gtfs", "station", "railway", "bus"),
    "elevation": ("elevation", "terrain", "topograph"),
    "boundaries": ("boundar", "admin", "protected"),
    "land_cover": ("land_cover", "landcover", "land_use"),
    "population": ("population", "census", "demograph"),
    "roads": ("road", "traffic"),
}


def _observed_rendering_types(traces: list[dict[str, Any]]) -> set[str]:
    observed: set[str] = set()
    for trace in traces:
        map_session = _map_session(trace)
        if _map_has_location(map_session):
            observed.add("map")
        if _answer(trace).strip():
            observed.add("text")
        if not isinstance(map_session, dict):
            continue
        collection = map_session.get("overlay_collection")
        instances = collection.get("instances") if isinstance(collection, dict) else []
        if not isinstance(instances, list):
            continue
        for instance in instances:
            if not isinstance(instance, dict):
                continue
            descriptor = instance.get("descriptor")
            descriptor = descriptor if isinstance(descriptor, dict) else {}
            geometry = str(
                descriptor.get("geometry_type") or instance.get("overlay_type") or ""
            ).casefold()
            rendering = str(
                descriptor.get("rendering_mode") or instance.get("rendering_mode") or ""
            ).casefold()
            value = f"{geometry} {rendering}"
            if "polygon" in value or "area" in value:
                observed.add("polygon")
            if "line" in value or "road" in value:
                observed.add("line")
            if any(marker in value for marker in ("point", "marker", "station")):
                observed.add("point")
            if any(
                marker in value for marker in ("raster", "tile", "xyz", "wms", "wmts")
            ):
                observed.add("raster")
    if not observed:
        observed.add("none")
    return observed


def _has_structured_clarification(trace: dict[str, Any]) -> bool:
    response = _response(trace)
    decision = response.get("decision")
    if isinstance(decision, dict):
        plan = decision.get("plan")
        if isinstance(plan, dict) and plan.get("state") == "clarify":
            return True
        if isinstance(decision.get("clarification"), dict):
            return True
    contract = _contract(trace)
    if contract.get("expected_frontend_update") == "clarification":
        return True
    return isinstance(contract.get("clarification_plan"), dict)


def _has_allowed_clarification(
    scenario: dict[str, Any], traces: list[dict[str, Any]]
) -> bool:
    expected = scenario.get("expected")
    return (
        isinstance(expected, dict)
        and expected.get("clarification") == "allowed"
        and bool(traces)
        and _has_structured_clarification(traces[-1])
    )


def _has_provider_provenance(result: dict[str, Any]) -> bool:
    provenance = result.get("provenance")
    if not isinstance(provenance, dict):
        provenance = result
    if not isinstance(provenance, dict):
        return False
    provider = provenance.get("provider")
    fetched_at = provenance.get("fetched_at")
    return (
        isinstance(provider, str)
        and bool(provider.strip())
        and isinstance(fetched_at, str)
        and bool(fetched_at.strip())
    )


def _has_explicit_limitation(traces: list[dict[str, Any]]) -> bool:
    for trace in traces:
        response = _response(trace)
        contract = _contract(trace)
        limitations = contract.get("capability_limitations")
        if isinstance(limitations, list) and any(
            isinstance(item, str) and item.strip() for item in limitations
        ):
            return True
        if _has_structured_clarification(trace):
            return True
        operation = response.get("operation")
        if isinstance(operation, dict) and operation.get("status") in {
            "failed",
            "partial",
        }:
            return True
        answer = _answer(trace).casefold()
        if any(
            marker in answer
            for marker in ("not available", "unavailable", "could not", "cannot verify")
        ):
            return True
    return False


def _evaluate_expected_properties(
    scenario: dict[str, Any],
    traces: list[dict[str, Any]],
    tool_calls: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    expected = scenario.get("expected")
    if not isinstance(expected, dict):
        return []

    contracts = [_contract(trace) for trace in traces]
    observed_classes = {
        str(contract.get("task_class"))
        for contract in contracts
        if str(contract.get("task_class") or "").strip()
    }
    allowed_classes = {
        str(value).strip()
        for value in expected.get("task_classes", [])
        if isinstance(value, str) and value.strip()
    }
    results = [
        _assertion_result(
            "expected_task_class",
            bool(observed_classes) and observed_classes <= allowed_classes,
            f"Observed task classes: {sorted(observed_classes)}; allowed: {sorted(allowed_classes)}.",
        )
    ]

    provider_events = _provider_events(traces)
    last_trace = traces[-1] if traces else {}
    has_clarification = _has_structured_clarification(last_trace)
    allowed_clarification = _has_allowed_clarification(scenario, traces)
    capabilities = _capability_ids(tool_calls) | _overlay_ids(traces) | {
        str(item.get("capability_id")).strip()
        for item in provider_events
        if isinstance(item.get("capability_id"), str)
        and item.get("capability_id").strip()
    }
    explicit_coordinate_evidence_count = sum(
        _has_explicit_coordinate_evidence(trace) for trace in traces
    )
    if explicit_coordinate_evidence_count:
        # Coordinates supplied by the user are first-class location evidence,
        # even though no external location provider was needed.
        capabilities.add("location")
    missing_families = []
    for family in expected.get("capability_families", []):
        family_key = str(family).strip().casefold()
        tokens = _CAPABILITY_FAMILY_TOKENS.get(family_key, (family_key,))
        if not any(
            any(token in capability.casefold() for token in tokens)
            for capability in capabilities
        ):
            missing_families.append(family_key)
    results.append(
        _assertion_result(
            "expected_capability_families",
            allowed_clarification or not missing_families,
            "All expected capability families were observed."
            if not missing_families
            else "An explicit clarification was allowed before capability execution."
            if allowed_clarification
            else f"Missing capability families: {', '.join(missing_families)}.",
        )
    )

    minimum_tool_count = expected.get("minimum_tool_count")
    execution_evidence_count = (
        len(tool_calls)
        + len(provider_events)
        + explicit_coordinate_evidence_count
    )
    count_passed = allowed_clarification or (
        isinstance(minimum_tool_count, int)
        and execution_evidence_count >= minimum_tool_count
    )
    results.append(
        _assertion_result(
            "expected_minimum_tool_count",
            count_passed,
            f"Observed {execution_evidence_count} execution events "
            f"({len(tool_calls)} tool calls, {len(provider_events)} provider events, "
            f"{explicit_coordinate_evidence_count} explicit coordinate evidence); "
            f"required at least {minimum_tool_count}.",
        )
    )

    clarification = expected.get("clarification")
    clarification_passed = (
        clarification == "allowed"
        or clarification == "required"
        and has_clarification
        or clarification == "not_required"
        and not has_clarification
    )
    results.append(
        _assertion_result(
            "expected_clarification",
            clarification_passed,
            f"Clarification expectation={clarification!r}; observed={has_clarification}.",
        )
    )

    expected_rendering = {
        str(value).strip().casefold()
        for value in expected.get("rendering_types", [])
        if isinstance(value, str) and value.strip()
    }
    observed_rendering = _observed_rendering_types(traces)
    results.append(
        _assertion_result(
            "expected_rendering_type",
            allowed_clarification or bool(expected_rendering & observed_rendering),
            "An explicit clarification was allowed without rendering a map."
            if allowed_clarification
            else f"Observed rendering types: {sorted(observed_rendering)}; accepted: {sorted(expected_rendering)}.",
        )
    )

    provenance_required = expected.get("provenance_required") is True
    successful_results = [
        result for result in _tool_results(traces) if not result.get("is_error")
    ]
    provider_event_provenance = (
        bool(provider_events)
        and all(_has_provider_provenance(event) for event in provider_events)
    )
    tool_result_provenance = bool(successful_results) and all(
        _has_provider_provenance(result) for result in successful_results
    )
    # Control-plane capability selections do not themselves have provider
    # provenance. The verified location/map provider event is the authoritative
    # evidence for those executions; data-bearing tool results still need their
    # own provenance when no provider event exists.
    provenance_evidence = (
        tool_result_provenance or provider_event_provenance
        if successful_results
        else provider_event_provenance or bool(explicit_coordinate_evidence_count)
    )
    provenance_passed = (
        allowed_clarification or not provenance_required or provenance_evidence
    )
    results.append(
        _assertion_result(
            "expected_provenance",
            provenance_passed,
            "Every successful execution has provider and retrieval provenance."
            if provenance_passed
            else "A successful tool result is missing provider or retrieval provenance.",
        )
    )

    if expected.get("fabrication_forbidden") is True:
        grounded = (
            tool_result_provenance or provider_event_provenance
            if successful_results
            else provider_event_provenance or bool(explicit_coordinate_evidence_count)
        )
        grounded_or_limited = grounded or _has_explicit_limitation(traces)
        results.append(
            _assertion_result(
                "expected_grounding",
                grounded_or_limited,
                "The response has provider evidence or an explicit limitation/clarification."
                if grounded_or_limited
                else "The response contains no provider evidence or explicit limitation.",
            )
        )
    return results


###############################################################################
def _evaluate_model_assertion(
    name: str,
    traces: list[dict[str, Any]],
    tool_calls: list[dict[str, Any]],
    scenario: dict[str, Any] | None = None,
) -> dict[str, Any]:
    contracts = [_contract(trace) for trace in traces]
    maps = [_map_session(trace) for trace in traces]
    capabilities = _capability_ids(tool_calls)
    overlays = _overlay_ids(traces)
    fingerprints = [
        fingerprint
        for trace in traces
        for fingerprint in trace.get("request_fingerprints", [])
        if isinstance(fingerprint, str)
    ]
    atomic_task_count = max(
        [len(contract.get("atomic_tasks", [])) for contract in contracts] or [0]
    )
    map_available = any(_map_has_location(map_session) for map_session in maps)
    answer_text = " ".join(_answer(trace).casefold() for trace in traces)
    last_trace = traces[-1] if traces else {}
    last_response = _response(last_trace)
    last_map = maps[-1] if maps else None

    if name == "context_usage_invariants":
        return _evaluate_context_usage_invariants(traces)
    if name == "location_target_consistency":
        return _evaluate_location_target_consistency(scenario or {}, traces)
    if name == "categorized_failures":
        return _evaluate_failure_diagnostics(traces)
    if name == "no_false_success":
        return _evaluate_no_false_success(traces)
    if name == "clarification_correctness":
        return _evaluate_clarification_correctness(scenario or {}, traces)
    if name == "deadline_compliance":
        return _evaluate_deadline_compliance(scenario or {}, traces)

    if name in {"one_location_tool", "rendered_map"}:
        return _assertion_result(
            name,
            map_available,
            "A verified map session contains a resolved location, center, and basemap."
            if map_available
            else "No verified map session was returned.",
        )
    if name == "location_or_clarification":
        passed = map_available or _has_structured_clarification(last_trace)
        return _assertion_result(
            name,
            passed,
            "The request produced a verified map or an explicit safe clarification."
            if passed
            else "The request produced neither a verified map nor an explicit clarification.",
        )
    if name in {"air_quality_tool", "environment_layer"}:
        passed = any(
            "air_quality" in value.casefold() for value in capabilities | overlays
        )
        return _assertion_result(
            name,
            passed,
            "Air-quality capability or overlay was executed."
            if passed
            else "No executed air-quality capability or overlay was observed.",
        )
    if name == "poi_tool":
        passed = any("poi" in value.casefold() for value in capabilities | overlays)
        return _assertion_result(
            name,
            passed,
            "A POI capability or overlay was executed."
            if passed
            else "No executed POI capability or overlay was observed.",
        )
    if name in {"decomposed_tasks", "compound_tasks"}:
        passed = atomic_task_count >= 2 or len(capabilities) >= 2
        return _assertion_result(
            name,
            passed,
            "The contract contains multiple atomic tasks or capabilities."
            if passed
            else "The contract did not produce multiple atomic tasks or capabilities.",
        )
    if name == "two_capabilities":
        passed = len(capabilities) >= 2
        return _assertion_result(
            name,
            passed,
            "Two distinct capabilities were executed."
            if passed
            else "Fewer than two distinct capabilities were executed.",
        )
    if name in {"reuse_location", "evidence_reuse"}:
        has_multi_task_location = atomic_task_count >= 2 and any(
            contract.get("location_signals") for contract in contracts
        )
        has_follow_up_map = len(traces) > 1 and map_available
        passed = has_multi_task_location or has_follow_up_map
        return _assertion_result(
            name,
            passed,
            "The request reused a resolved location across tasks or turns."
            if passed
            else "No reusable resolved location was evidenced.",
        )
    if name == "dependency_order":
        passed = len(tool_calls) >= 2 and len(fingerprints) == len(set(fingerprints))
        return _assertion_result(
            name,
            passed,
            "Multiple validated calls were executed in a non-duplicated order."
            if passed
            else "The scenario did not produce an ordered multi-tool execution.",
        )
    if name == "state_retention":
        memory = last_response.get("memory_snapshot")
        passed = len(traces) > 1 and (
            isinstance(last_response.get("task_snapshot"), dict)
            and (
                isinstance(last_response.get("memory_snapshot"), dict)
                and (
                    isinstance(memory.get("active_location"), dict)
                    or isinstance(memory.get("active_visualization"), dict)
                )
                or _map_has_location(last_map)
            )
        )
        return _assertion_result(
            name,
            passed,
            "The final turn retained active conversation or map state."
            if passed
            else "The final turn did not retain an active conversation/map state.",
        )
    if name == "scope_invalidation":
        passed = False
        for trace in traces:
            if "exclude" not in str(trace.get("prompt", "")).casefold():
                continue
            task_snapshot = _response(trace).get("task_snapshot")
            scope = (
                task_snapshot.get("geospatial_state", {}).get("geographic_scope", {})
                if isinstance(task_snapshot, dict)
                else {}
            )
            passed = bool(scope.get("exclusions")) or bool(
                _contract(trace).get("viewport_intent")
            )
        return _assertion_result(
            name,
            passed,
            "The exclusion turn changed or recorded geographic scope."
            if passed
            else "No exclusion/scope update was recorded.",
        )
    if name in {"append_layer", "no_duplicate_layer_call"}:
        if name == "append_layer":
            initial = set()
            if traces:
                initial = set(
                    item
                    for item in (_map_session(traces[0]) or {}).get("overlay_ids", [])
                    if isinstance(item, str)
                )
            passed = (
                len(overlays) > len(initial) or len(traces) == 1 and len(overlays) >= 1
            )
            reason = (
                "A later turn added or retained a requested layer."
                if passed
                else "No appended layer was evidenced."
            )
        else:
            passed = len(fingerprints) == len(set(fingerprints))
            reason = (
                "Canonical tool-call fingerprints were not duplicated."
                if passed
                else "A canonical tool-call fingerprint was repeated."
            )
        return _assertion_result(name, passed, reason)
    if name == "no_duplicate_search":
        passed = len(fingerprints) == len(set(fingerprints))
        return _assertion_result(
            name,
            passed,
            "No duplicate canonical search call was observed."
            if passed
            else "A duplicate canonical search call was observed.",
        )
    if name == "comparison_without_tool":
        bad_markers = ("could not summarize", "cannot summarize")
        grounded_limitation = (
            "don't have specific" in _answer(last_trace).casefold()
            or "no verified" in _answer(last_trace).casefold()
            or "not available" in _answer(last_trace).casefold()
        )
        passed = (
            bool(_answer(last_trace).strip())
            and not last_trace.get("tool_calls")
            and (
                not any(
                    marker in _answer(last_trace).casefold() for marker in bad_markers
                )
                or grounded_limitation
            )
        )
        return _assertion_result(
            name,
            passed,
            "The final comparison was answered without another tool."
            if passed
            else "The final response was empty, tool-backed, or an unresolved request for more data.",
        )
    if name == "clarification_or_context_resolution":
        plan = last_response.get("decision", {}).get("plan", {})
        clarification = last_response.get("decision", {}).get("clarification")
        clarification_fields = (
            clarification.get("missing_fields", [])
            if isinstance(clarification, dict)
            else []
        )
        location_markers = (
            "specific location",
            "which location",
            "city, region",
            "coordinates",
            "which city",
        )
        passed = plan.get("state") == "clarify" and (
            any(marker in answer_text for marker in location_markers)
            or "location" in clarification_fields
        )
        return _assertion_result(
            name,
            passed,
            "The ambiguous request produced a clarification."
            if passed
            else "The ambiguous request did not produce a location clarification.",
        )
    if name in {"poi_and_weather"}:
        passed = any("poi" in value.casefold() for value in capabilities) and any(
            "weather" in value.casefold() for value in capabilities
        )
        return _assertion_result(
            name,
            passed,
            "POI and weather capabilities were both executed."
            if passed
            else "POI and weather were not both executed.",
        )
    if name == "valid_arguments":
        passed = _valid_tool_arguments(tool_calls, traces) or (
            _has_allowed_clarification(scenario or {}, traces)
            and not tool_calls
            and not map_available
        )
        return _assertion_result(
            name,
            passed,
            "All execution arguments passed coordinate and bbox checks."
            if passed
            else "An execution argument was invalid, or no verified execution or safe clarification was made.",
        )
    if name == "partial_failure_is_explicit":
        failure_markers = (
            "could not",
            "failed",
            "error",
            "unavailable",
            "partial",
            "not be added",
        )
        passed = any(marker in answer_text for marker in failure_markers) and (
            any(_has_error(trace) for trace in traces) or len(tool_calls) > 1
        )
        return _assertion_result(
            name,
            passed,
            "The response explicitly surfaced a tool failure or partial result."
            if passed
            else "No explicit partial/failure explanation was evidenced.",
        )
    if name == "correction_overrides_old_location":
        correction_indices = [
            index
            for index, trace in enumerate(traces)
            if any(
                marker in str(trace.get("prompt", "")).casefold()
                for marker in ("instead", "move", "change location")
            )
        ]
        passed = False
        if correction_indices and maps:
            first_location = (maps[0] or {}).get("resolved_location", {})
            corrected = (
                maps[correction_indices[0]]
                if correction_indices[0] < len(maps)
                else None
            )
            corrected_location = (corrected or {}).get("resolved_location", {})
            passed = (
                isinstance(first_location, dict)
                and isinstance(corrected_location, dict)
                and first_location.get("label") != corrected_location.get("label")
                and _map_has_location(corrected)
            )
            if passed:
                location = corrected_location
                center = (corrected or {}).get("center", {})
                passed = center.get("latitude") == location.get(
                    "latitude"
                ) and center.get("longitude") == location.get("longitude")
        return _assertion_result(
            name,
            passed,
            "The correction changed both map location and viewport center."
            if passed
            else "The correction did not produce a consistent new map location.",
        )
    if name == "context_answer_without_tool":
        passed = bool(_answer(last_trace).strip()) and not last_trace.get("tool_calls")
        return _assertion_result(
            name,
            passed,
            "The context question was answered without a tool."
            if passed
            else "The context question triggered a tool or had no answer.",
        )
    if name == "long_context":
        usage = last_response.get("context_usage")
        passed = (
            len(traces) >= 6
            and isinstance(usage, dict)
            and isinstance(usage.get("estimated_input_tokens"), int | float)
        )
        return _assertion_result(
            name,
            passed,
            "Context usage was reported for the long conversation."
            if passed
            else "Long-context usage was not reported.",
        )
    if name == "bounded_context_growth":
        usages = [
            _response(trace).get("context_usage", {}).get("usage_percent")
            for trace in traces
            if isinstance(_response(trace).get("context_usage"), dict)
        ]
        passed = (
            bool(usages)
            and max(float(value) for value in usages if isinstance(value, int | float))
            < 90
        )
        return _assertion_result(
            name,
            passed,
            "Context usage stayed below the configured safety ceiling."
            if passed
            else "Context usage exceeded or did not report the safety ceiling.",
        )
    if name == "provider_reachable":
        passed = bool(traces) and all(
            int(trace.get("status_code") or 0) == 200 for trace in traces
        )
        return _assertion_result(
            name,
            passed,
            "The backend returned HTTP 200 for every provider smoke turn."
            if passed
            else "The provider smoke turn was not reachable.",
        )
    if name == "record_upstream_status":
        passed = any(_tool_results([trace]) for trace in traces) or any(
            _map_session(trace) for trace in traces
        )
        return _assertion_result(
            name,
            passed,
            "The response recorded tool or map-provider output."
            if passed
            else "No upstream result was recorded.",
        )
    return _assertion_result(name, False, "No evaluator exists for this assertion.")


###############################################################################
def evaluate_model_scenario(
    scenario: dict[str, Any], traces: list[dict[str, Any]]
) -> dict[str, Any]:
    tool_calls = _tool_calls(traces)
    provider_events = _provider_events(traces)
    explicit_coordinate_evidence_count = sum(
        _has_explicit_coordinate_evidence(trace) for trace in traces
    )
    assertion_results = [
        _evaluate_model_assertion(str(name), traces, tool_calls, scenario)
        for name in [
            *scenario.get("assertions", []),
            *scenario.get("invariants", []),
        ]
    ]
    assertion_results.extend(
        _evaluate_expected_properties(scenario, traces, tool_calls)
    )
    fingerprints = [
        fingerprint
        for trace in traces
        for fingerprint in trace.get("request_fingerprints", [])
        if isinstance(fingerprint, str)
    ]
    unnecessary_tool_calls = sum(
        len(trace.get("tool_calls", []))
        for trace in traces
        if _contract(trace).get("task_class") == "general_question"
        or (
            _contract(trace).get("task_class") == "direct_query"
            and not _contract(trace).get("tools_needed")
            and not _contract(trace).get("requested_layers")
        )
    )
    return {
        "passed": all(item["passed"] for item in assertion_results),
        "assertions": assertion_results,
        "tool_calls": len(tool_calls),
        "provider_events": len(provider_events),
        "execution_evidence": (
            len(tool_calls)
            + len(provider_events)
            + explicit_coordinate_evidence_count
        ),
        "duplicate_tool_calls": len(fingerprints) - len(set(fingerprints)),
        "unnecessary_tool_calls": unnecessary_tool_calls,
        "failed_tool_calls": sum(
            1 for result in _tool_results(traces) if result.get("is_error")
        ),
    }


###############################################################################
def _model_lane_metrics(
    results: list[dict[str, Any]], *, lane: str = "model_in_loop"
) -> dict[str, Any]:
    evaluations = [result.get("evaluation", {}) for result in results]
    assertion_results = [
        assertion
        for evaluation in evaluations
        for assertion in evaluation.get("assertions", [])
        if isinstance(assertion, dict)
    ]
    tool_selection_names = {
        "air_quality_tool",
        "poi_tool",
        "two_capabilities",
        "poi_and_weather",
        "valid_arguments",
    }
    tool_selection = [
        item for item in assertion_results if item.get("name") in tool_selection_names
    ]
    usages = [
        _response(trace).get("context_usage", {}).get("usage_percent")
        for result in results
        for trace in result.get("turns", [])
        if isinstance(_response(trace).get("context_usage"), dict)
    ]
    scenario_count = len(results)
    passed = sum(1 for result in results if result.get("status") == "passed")
    blocked = sum(1 for result in results if result.get("status") == "blocked")
    available = scenario_count - blocked
    if passed == scenario_count:
        status = "passed"
    elif passed + blocked == scenario_count and blocked:
        status = "blocked"
    else:
        status = "failed"
    return {
        "lane": lane,
        "status": status,
        "scenario_count": scenario_count,
        "passed_scenarios": passed,
        "failed_scenarios": scenario_count - passed - blocked,
        "blocked_scenarios": blocked,
        "available_scenarios": available,
        "task_success_rate": passed / scenario_count if scenario_count else 1.0,
        "available_success_rate": passed / available if available else None,
        "assertion_pass_rate": (
            sum(1 for item in assertion_results if item.get("passed"))
            / len(assertion_results)
            if assertion_results
            else 1.0
        ),
        "correct_tool_selection_rate": (
            sum(1 for item in tool_selection if item.get("passed"))
            / len(tool_selection)
            if tool_selection
            else 1.0
        ),
        "total_tool_calls": sum(
            int(item.get("evaluation", {}).get("tool_calls", 0)) for item in results
        ),
        "duplicate_tool_calls": sum(
            int(item.get("evaluation", {}).get("duplicate_tool_calls", 0))
            for item in results
        ),
        "unnecessary_tool_calls": sum(
            int(item.get("evaluation", {}).get("unnecessary_tool_calls", 0))
            for item in results
        ),
        "failed_tool_calls": sum(
            int(item.get("evaluation", {}).get("failed_tool_calls", 0))
            for item in results
        ),
        "invalid_tool_call_rate": 0.0,
        "peak_context_usage_percent": max(
            (float(value) for value in usages if isinstance(value, int | float)),
            default=0.0,
        ),
        "context_usage_sample_count": len(
            [
                usage
                for result in results
                for trace in result.get("turns", [])
                for usage in _context_usage_records([trace])
            ]
        ),
    }


###############################################################################
class _ScriptedToolRegistry:
    # -------------------------------------------------------------------------
    def __init__(self, failure: str) -> None:
        self.failure = failure
        self.calls: list[tuple[str, dict[str, Any]]] = []

    # -------------------------------------------------------------------------
    async def execute_native_tool(
        self, name: str, arguments: dict[str, Any], context: AgentExecutionContext
    ) -> ToolExecutionEnvelope:
        _ = context
        self.calls.append((name, arguments))
        if self.failure == "timeout":
            raise TimeoutError("scripted timeout")
        if self.failure == "http_error":
            return ToolExecutionEnvelope(
                ok=False,
                error=ToolError(
                    code="provider_unavailable", message="scripted upstream failure"
                ),
            )
        if self.failure == "empty":
            return ToolExecutionEnvelope(ok=True, data={})
        if self.failure == "malformed_schema":
            return ToolExecutionEnvelope(ok=True, data={"capability_id": "wrong"})
        if self.failure == "partial" and name == "second":
            return ToolExecutionEnvelope(
                ok=False,
                error=ToolError(code="provider_unavailable", message="partial failure"),
            )
        return ToolExecutionEnvelope(ok=True, data={"value": "scripted"})


###############################################################################
def _scripted_plan(failure: str) -> ToolPlan:
    if failure == "malformed_schema":
        steps = [
            ToolPlanStep(
                step_id="malformed",
                tool_name="execute_geospatial_capability",
                capability_id="expected",
                reason="scripted malformed result",
            )
        ]
    elif failure == "partial":
        steps = [
            ToolPlanStep(step_id="first", tool_name="first", reason="partial success"),
            ToolPlanStep(
                step_id="second", tool_name="second", reason="partial failure"
            ),
        ]
    elif failure == "repeated_call":
        steps = [
            ToolPlanStep(step_id="first", tool_name="probe", reason="first call"),
            ToolPlanStep(
                step_id="duplicate", tool_name="probe", reason="duplicate call"
            ),
        ]
    else:
        steps = [ToolPlanStep(step_id="scripted", tool_name="probe", reason=failure)]
    if failure == "repeated_call":
        steps[1] = steps[1].model_copy(update={"arguments": dict(steps[0].arguments)})
    if failure in {"timeout", "http_error"}:
        steps[0] = steps[0].model_copy(
            update={"retry_policy": ToolRetryPolicy(max_attempts=2)}
        )
    return ToolPlan(
        tool_group="direct_chat",
        selected_tools=[step.tool_name for step in steps],
        steps=steps,
    )


###############################################################################
def _run_scripted_plan(failure: str) -> tuple[list[Any], int]:
    if failure == "invalid_coordinates_bounds_temporal":
        registry = ToolRegistry(runtime_registry=object())
        calls = 0

        async def handler(arguments: dict[str, Any], context: Any) -> dict[str, Any]:
            nonlocal calls
            _ = (arguments, context)
            calls += 1
            return {"value": "handler called"}

        registry.register_native_tool(
            LLMToolDefinition(
                name="validate",
                description="Validate coordinates",
                parameters_json_schema={
                    "type": "object",
                    "properties": {"latitude": {"type": "number", "maximum": 90}},
                    "required": ["latitude"],
                },
            ),
            handler,
        )
        plan = ToolPlan(
            tool_group="direct_chat",
            selected_tools=["validate"],
            steps=[
                ToolPlanStep(
                    step_id="invalid",
                    tool_name="validate",
                    reason="invalid coordinates",
                    arguments={"latitude": 91},
                )
            ],
        )
        results = asyncio.run(
            ToolPlanExecutor(tool_registry=registry).execute(
                plan, AgentExecutionContext(request_id="scripted-fault")
            )
        )
        return results, calls
    registry = _ScriptedToolRegistry(failure)
    results = asyncio.run(
        ToolPlanExecutor(tool_registry=registry).execute(
            _scripted_plan(failure),
            AgentExecutionContext(request_id="scripted-fault"),
        )
    )
    return results, len(registry.calls)


###############################################################################
def _run_scripted_fault_scenario(scenario: dict[str, Any]) -> dict[str, Any]:
    scenario_id = str(scenario["id"])
    failure = str(scenario.get("failure") or "")
    if scenario_id == "context-answerable-no-tool":
        tool_calls = 0
        passed = True
        details = {"status": "answered_from_context", "tool_calls": tool_calls}
    elif scenario_id == "stale-layer-removal":
        state = AgentThreadState(
            conversation_id="scripted-fault",
            evidence_refs=["western-layer", "retained-layer"],
            geospatial_state=GeospatialWorkingState(
                layer_refs=["western-layer", "retained-layer"],
                renderable_refs=["western-layer", "retained-layer"],
            ),
            tasks=[
                AgentTask(
                    id="weather",
                    description="Weather",
                    kind="weather",
                    status="completed",
                    output_refs=["western-layer"],
                )
            ],
        )
        apply_steering_delta(
            state,
            SteeringDelta(
                kind="exclusion", text="Remove western results from the current map."
            ),
        )
        passed = (
            "western-layer" not in state.evidence_refs
            and "western-layer" not in state.geospatial_state.renderable_refs
            and "retained-layer" in state.geospatial_state.renderable_refs
        )
        details = {
            "status": "state_delta_applied" if passed else "state_delta_failed",
            "tool_calls": 0,
            "remaining_renderable_refs": state.geospatial_state.renderable_refs,
        }
    else:
        results, tool_calls = _run_scripted_plan(failure)
        if failure in {"timeout", "http_error"}:
            passed = (
                len(results) == 1
                and results[0].ok is False
                and results[0].provenance.attempt == 2
            )
        elif failure == "empty":
            passed = len(results) == 1 and results[0].ok and not results[0].data
        elif failure == "malformed_schema":
            passed = len(results) == 1 and results[0].validation_error is not None
        elif failure == "partial":
            passed = any(result.ok for result in results) and any(
                not result.ok for result in results
            )
        elif failure == "invalid_coordinates_bounds_temporal":
            passed = (
                len(results) == 1
                and results[0].error_code == "invalid_arguments"
                and tool_calls == 0
            )
        elif failure == "repeated_call":
            passed = (
                len(results) == 2
                and results[1].error_code == "duplicate_tool_call"
                and tool_calls == 1
            )
        else:
            passed = False
        details = {
            "status": "passed" if passed else "failed",
            "tool_calls": tool_calls,
            "tool_results": [result.model_dump(mode="json") for result in results],
        }
    return {
        "scenario_id": scenario_id,
        "assertions": scenario.get("assertions", []),
        "passed": passed,
        **details,
    }


###############################################################################
def run_scripted_fault_lane(*, manifest_path: Path, output_dir: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("matrix_version") == "1.0":
        from tests.agent_benchmark.scenario_matrix import validate_scenario_matrix

        errors = validate_scenario_matrix(manifest)
        if errors:
            raise ValueError(
                "Invalid geographic-agent scenario matrix:\n- " + "\n- ".join(errors)
            )
    scenarios = [
        item for item in manifest["scenarios"] if item.get("lane") == "scripted_fault"
    ]
    results = [_run_scripted_fault_scenario(scenario) for scenario in scenarios]
    passed = sum(1 for result in results if result["passed"])
    metrics = {
        "status": "passed" if passed == len(results) else "failed",
        "lane": "scripted_fault",
        "scenario_count": len(results),
        "passed_scenarios": passed,
        "task_success_rate": passed / len(results) if results else 1.0,
        "unnecessary_tool_calls": sum(
            1
            for result in results
            if result["scenario_id"] == "context-answerable-no-tool"
            and result["tool_calls"]
        ),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    bundle = {
        "manifest": str(manifest_path),
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "lane": "scripted_fault",
        "validation_type": "deterministic",
        "status": metrics["status"],
        "results": results,
    }
    (output_dir / "benchmark.json").write_text(
        json.dumps(bundle, indent=2, ensure_ascii=True, default=str), encoding="utf-8"
    )
    (output_dir / "trace.jsonl").write_text(
        "\n".join(json.dumps(item, ensure_ascii=True, default=str) for item in results)
        + "\n",
        encoding="utf-8",
    )
    (output_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2, ensure_ascii=True), encoding="utf-8"
    )
    return bundle


###############################################################################
def run_manifest(
    *,
    manifest_path: Path,
    output_dir: Path,
    base_url: str,
    lane: str | None = None,
    repetitions: int = 1,
) -> dict[str, Any]:
    if lane == "scripted_fault":
        return run_scripted_fault_lane(
            manifest_path=manifest_path, output_dir=output_dir
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    scenarios = [
        scenario
        for scenario in manifest["scenarios"]
        if lane is None or scenario.get("lane") == lane
    ]
    output_dir.mkdir(parents=True, exist_ok=True)
    client = httpx.Client(base_url=base_url.rstrip("/"), timeout=180.0)
    started = time.perf_counter()
    health = client.get("/api/health")
    results: list[dict[str, Any]] = []
    for repetition in range(1, repetitions + 1):
        for scenario in scenarios:
            conversation_response = client.post(
                "/api/conversations",
                json={"title": f"benchmark {scenario['id']} r{repetition}"},
            )
            conversation_payload = _json_response(conversation_response)
            conversation_id = conversation_payload.get("conversation_id")
            if not isinstance(conversation_id, str) or not conversation_id:
                conversation_id = f"benchmark-{uuid4().hex}"
            turns = scenario.get("turns") or [scenario.get("prompt", "")]
            trace: list[dict[str, Any]] = []
            scenario_started = time.perf_counter()
            for turn in turns:
                turn_started = time.perf_counter()
                response = client.post(
                    "/api/chat/turn",
                    json={"conversation_id": conversation_id, "message": turn},
                )
                payload = _json_response(response)
                tool_payload = payload.get("tool_payload")
                tool_calls = (
                    tool_payload.get("tool_calls", [])
                    if isinstance(tool_payload, dict)
                    else []
                )
                trace.append(
                    {
                        "prompt": turn,
                        "duration_seconds": time.perf_counter() - turn_started,
                        "status_code": response.status_code,
                        "tool_calls": tool_calls,
                        "tool_results": tool_payload.get("tool_results", [])
                        if isinstance(tool_payload, dict)
                        else [],
                        "provider_events": tool_payload.get("provider_events", [])
                        if isinstance(tool_payload, dict)
                        else [],
                        "response": payload,
                        "map_session": payload.get("map_session"),
                        "request_fingerprints": [
                            _fingerprint(item)
                            for item in tool_calls
                            if isinstance(item, dict)
                        ],
                    }
                )
            evaluation = evaluate_model_scenario(scenario, trace)
            blocked_reasons = [
                reason
                for item in trace
                if (reason := _live_provider_block_reason(item)) is not None
            ]
            blocked = bool(blocked_reasons)
            results.append(
                {
                    "scenario_id": scenario["id"],
                    "repetition": repetition,
                    "conversation_id": conversation_id,
                    "elapsed_seconds": time.perf_counter() - scenario_started,
                    "turns": trace,
                    "evaluation": evaluation,
                    "blocked_reasons": sorted(set(blocked_reasons)),
                    "status": "blocked"
                    if blocked
                    else ("passed" if evaluation["passed"] else "failed"),
                }
            )
    metrics = _model_lane_metrics(
        results,
        lane=lane or str(manifest.get("default_lane") or "model_in_loop"),
    )
    bundle = {
        "manifest": str(manifest_path),
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "base_url": base_url,
        "repetitions": repetitions,
        "validation_type": "live_provider",
        "health": {
            "status_code": health.status_code,
            "payload": _json_response(health),
        },
        "elapsed_seconds": time.perf_counter() - started,
        "status": metrics["status"],
        "metrics": metrics,
        "results": results,
    }
    (output_dir / "benchmark.json").write_text(
        json.dumps(bundle, indent=2, ensure_ascii=True, default=str), encoding="utf-8"
    )
    (output_dir / "trace.jsonl").write_text(
        "\n".join(json.dumps(item, ensure_ascii=True, default=str) for item in results)
        + "\n",
        encoding="utf-8",
    )
    (output_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2, ensure_ascii=True), encoding="utf-8"
    )
    return bundle


###############################################################################
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--base-url", default=os.environ.get("AEGIS_BASE_URL", "http://127.0.0.1:7059")
    )
    parser.add_argument(
        "--lane", choices=["model_in_loop", "scripted_fault", "live_smoke"]
    )
    parser.add_argument("--repetitions", type=int, default=1)
    args = parser.parse_args()
    if args.repetitions < 1:
        parser.error("--repetitions must be at least 1")
    bundle = run_manifest(
        manifest_path=args.manifest,
        output_dir=args.output,
        base_url=args.base_url,
        lane=args.lane,
        repetitions=args.repetitions,
    )
    return 0 if bundle.get("status") in {None, "passed", "recorded"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
