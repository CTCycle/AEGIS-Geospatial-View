"""Capture request-level evidence for live public raster rendering.

This test intentionally records both successful and failed raster requests. It
does not turn a provider failure into a passing map acknowledgement; the
persisted UI outcome remains the acceptance authority.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit

import pytest
from playwright.sync_api import ConsoleMessage, Page, expect

from tests.e2e.helpers.artifacts import (
    ensure_test_artifact_dirs,
    write_log_tail,
    write_snapshot,
)


TEST_ID = "RASTER-LIVE-DIAGNOSTICS"
MAX_EVENTS = 512
MAX_TEXT = 8000
RASTER_HOSTS = {
    "hazards.fema.gov",
    "services.terrascope.be",
    "titiler.terrascope.be",
    "mapproxy.terrascope.be",
    "gibs.earthdata.nasa.gov",
}
SENSITIVE_QUERY_MARKERS = (
    "api_key",
    "apikey",
    "authorization",
    "credential",
    "password",
    "secret",
    "token",
)
SCENARIOS = (
    (
        "fema_new_orleans",
        "Show standalone FEMA NFHL flood zones for New Orleans, Louisiana.",
    ),
    (
        "esa_worldcover_rome",
        "Show standalone ESA WorldCover for Rome, Italy.",
    ),
)
SCENARIO_CAPABILITIES = {
    "fema_new_orleans": "fema_nfhl_flood_zones",
    "esa_worldcover_rome": "esa_worldcover",
}
TARGET_LABEL_HINTS: dict[str, tuple[str, ...]] = {
    "fema_nfhl_flood_zones": ("fema",),
    "esa_worldcover": ("worldcover",),
    "IMERG_Precipitation_Rate": ("imerg", "precipitation"),
    "MODIS_Combined_L3_IGBP_Land_Cover_Type_Annual": ("land cover",),
    "MODIS_Combined_Thermal_Anomalies_Fire": ("fire", "thermal anomaly"),
    "MODIS_Terra_Aerosol": ("aerosol",),
    "MODIS_Terra_L3_Land_Water_Mask": ("land and water", "water mask"),
    "MODIS_Terra_Land_Surface_Temp_Day": ("daytime", "surface temperature"),
    "MODIS_Terra_Land_Surface_Temp_Night": ("nighttime", "surface temperature"),
    "MODIS_Terra_NDVI_8Day": ("ndvi", "vegetation index"),
    "OMPS_Ozone_Total_Column": ("ozone",),
    "SRTM_Color_Index": ("srtm", "color index"),
    "VIIRS_SNPP_CorrectedReflectance_TrueColor": ("true color", "corrected reflectance"),
    "VIIRS_SNPP_DayNightBand_ENCC": (
        "day-night",
        "day night",
        "nighttime lights",
    ),
}


def _bounded_text(value: str) -> str:
    return " ".join(value.split())[:MAX_TEXT]


def _sanitize_url(raw_url: str) -> str:
    parsed = urlsplit(raw_url)
    query: list[tuple[str, str]] = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        if any(marker in key.casefold() for marker in SENSITIVE_QUERY_MARKERS):
            value = "[REDACTED]"
        query.append((key, value))
    return urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urlencode(query, doseq=True), "")
    )


def _raster_transport(url: str) -> str | None:
    parsed = urlsplit(url)
    if parsed.path.startswith("/api/geospatial/tiles/"):
        return "aegis_proxy"
    if (parsed.hostname or "").casefold() in RASTER_HOSTS:
        return "direct_upstream"
    return None


def _proxy_capability_id(url: str) -> str | None:
    path_parts = [unquote(part) for part in urlsplit(url).path.split("/")]
    try:
        proxy_index = path_parts.index("tiles")
    except ValueError:
        return None
    if proxy_index + 1 >= len(path_parts):
        return None
    capability_id = path_parts[proxy_index + 1].strip()
    return capability_id or None


def _request_failure(request: Any) -> str | None:
    failure = getattr(request, "failure", None)
    if callable(failure):
        failure = failure()
    if isinstance(failure, dict):
        return _bounded_text(str(failure.get("errorText") or failure))
    if failure is not None:
        return _bounded_text(str(failure))
    return None


def _safe_trace_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


class _RasterCapture:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self.console: list[dict[str, str]] = []
        self.page_errors: list[str] = []

    def _append(self, event: dict[str, Any]) -> None:
        if len(self.events) < MAX_EVENTS:
            self.events.append(event)

    def attach(self, page: Page) -> None:
        def on_request(request: Any) -> None:
            transport = _raster_transport(request.url)
            if transport is not None:
                self._append(
                    {
                        "kind": "request",
                        "transport": transport,
                        "method": request.method,
                        "resource_type": request.resource_type,
                        "capability_id": _proxy_capability_id(request.url),
                        "url": _sanitize_url(request.url),
                    }
                )

        def on_response(response: Any) -> None:
            transport = _raster_transport(response.url)
            if transport is not None:
                self._append(
                    {
                        "kind": "response",
                        "transport": transport,
                        "resource_type": response.request.resource_type,
                        "status": response.status,
                        "content_type": response.headers.get("content-type"),
                        "capability_id": _proxy_capability_id(response.url),
                        "url": _sanitize_url(response.url),
                    }
                )

        def on_request_failed(request: Any) -> None:
            transport = _raster_transport(request.url)
            if transport is not None:
                self._append(
                    {
                        "kind": "requestfailed",
                        "transport": transport,
                        "method": request.method,
                        "resource_type": request.resource_type,
                        "failure": _request_failure(request),
                        "capability_id": _proxy_capability_id(request.url),
                        "url": _sanitize_url(request.url),
                    }
                )

        def on_console(message: ConsoleMessage) -> None:
            if len(self.console) < MAX_EVENTS:
                self.console.append(
                    {"type": message.type, "text": _bounded_text(message.text)}
                )

        def on_page_error(error: Any) -> None:
            if len(self.page_errors) < MAX_EVENTS:
                self.page_errors.append(_bounded_text(str(error)))

        page.on("request", on_request)
        page.on("response", on_response)
        page.on("requestfailed", on_request_failed)
        page.on("console", on_console)
        page.on("pageerror", on_page_error)


def _provider_probe(page: Page, api_base_url: str) -> dict[str, Any]:
    response = page.request.post(
        f"{api_base_url.rstrip('/')}/api/chat/models/structured-probe",
        timeout=60_000,
    )
    try:
        body = response.json()
    except (TypeError, ValueError):
        body = {}
    body = body if isinstance(body, dict) else {}
    return {
        "http_status": response.status,
        "provider": body.get("provider"),
        "model": body.get("model"),
        "protocol": body.get("protocol"),
        "status": body.get("status"),
        "parse_status": body.get("parse_status"),
        "duration_ms": body.get("duration_ms"),
    }


def _read_conversation_id(page: Page) -> str | None:
    raw = page.evaluate(
        "() => window.sessionStorage.getItem('aegis:webapp-ui-state:v1')"
    )
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return None
    chat_page = data.get("chatPage", {}) if isinstance(data, dict) else {}
    chat_panel = chat_page.get("chatPanel", {}) if isinstance(chat_page, dict) else {}
    conversation_id = chat_panel.get("conversationId")
    return (
        conversation_id
        if isinstance(conversation_id, str) and conversation_id.strip()
        else None
    )


def _read_latest_run_trace(
    page: Page, api_base_url: str, conversation_id: str | None
) -> dict[str, Any]:
    if not conversation_id:
        return {"status": "conversation_id_unavailable"}
    snapshot_response = page.request.get(
        f"{api_base_url.rstrip('/')}/api/conversations/{conversation_id}",
        timeout=30_000,
    )
    if snapshot_response.status != 200:
        return {"status": "snapshot_unavailable", "http_status": snapshot_response.status}
    try:
        snapshot = snapshot_response.json()
    except (TypeError, ValueError):
        return {"status": "snapshot_invalid"}
    recent_runs = snapshot.get("recent_runs") if isinstance(snapshot, dict) else None
    if not isinstance(recent_runs, list) or not recent_runs:
        return {"status": "run_unavailable", "conversation_id": conversation_id}
    latest = recent_runs[0] if isinstance(recent_runs[0], dict) else {}
    run_id = latest.get("run_id")
    run_version = latest.get("run_version")
    if not isinstance(run_id, str) or not run_id:
        return {"status": "run_id_unavailable", "conversation_id": conversation_id}
    version_query = (
        f"&run_version={int(run_version)}"
        if isinstance(run_version, int) and run_version > 0
        else ""
    )
    trace_response = page.request.get(
        f"{api_base_url.rstrip('/')}/api/conversations/{conversation_id}"
        f"/runs/{run_id}/trace?limit=200&include_internal=true{version_query}",
        timeout=30_000,
    )
    if trace_response.status != 200:
        return {
            "status": "trace_unavailable",
            "conversation_id": conversation_id,
            "run_id": run_id,
            "run_version": run_version,
            "http_status": trace_response.status,
        }
    try:
        trace = trace_response.json()
    except (TypeError, ValueError):
        return {
            "status": "trace_invalid",
            "conversation_id": conversation_id,
            "run_id": run_id,
            "run_version": run_version,
        }
    return _summarize_run_trace(
        conversation_id=conversation_id,
        run_id=run_id,
        run_version=run_version,
        run_summary=latest,
        events=trace.get("events", []) if isinstance(trace, dict) else [],
    )


def _summarize_run_trace(
    *,
    conversation_id: str,
    run_id: str,
    run_version: Any,
    run_summary: dict[str, Any],
    events: Any,
) -> dict[str, Any]:
    safe_events = [item for item in events if isinstance(item, dict)]
    selected_tools: list[str] = []
    tool_results: list[dict[str, Any]] = []
    exposed_by_iteration: dict[str, list[str]] = {}
    capability_ids: list[str] = []
    evidence_refs: list[str] = []
    apply_map_plan_attempts = 0
    render_preparation: list[dict[str, Any]] = []
    iteration_count = 0
    model_call_count = 0
    tool_call_count = 0
    state_transition_count = 0
    route: dict[str, Any] = {}
    temporal_evidence: dict[str, Any] = {}
    terminal_reason = run_summary.get("state")

    def add_unique(target: list[str], value: Any) -> None:
        if (
            isinstance(value, str)
            and value.strip()
            and value not in {"[depth-limited]", "[truncated]", "[redacted]"}
            and value not in target
        ):
            target.append(value)

    def collect_safe_ids(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "evidence_refs" and isinstance(item, list):
                    for reference in item:
                        add_unique(evidence_refs, reference)
                elif key == "route" and isinstance(item, dict):
                    route.update(
                        {
                            field: item.get(field)
                            for field in (
                                "primary_domain",
                                "secondary_domains",
                                "task_mode",
                                "route_id",
                                "operation",
                                "target_refs",
                                "temporal_scope",
                            )
                            if item.get(field) is not None
                        }
                    )
                if key == "run_state":
                    continue
                collect_safe_ids(item)
            return
        if isinstance(value, list):
            for item in value:
                collect_safe_ids(item)

    def collect_selected_capabilities(value: Any) -> None:
        """Collect execution/map capabilities while excluding discovery catalogs."""
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {"capability_id", "capabilityId"}:
                    add_unique(capability_ids, item)
                elif key in {"selected_capability_ids", "selectedCapabilityIds"}:
                    if isinstance(item, list):
                        for capability_id in item:
                            add_unique(capability_ids, capability_id)
                elif key in {
                    "capabilities",
                    "available_capabilities",
                    "catalog",
                    "items",
                    "layers",
                    "manifest",
                    "matched_capabilities",
                    "results",
                }:
                    continue
                else:
                    collect_selected_capabilities(item)
            return
        if isinstance(value, list):
            for item in value:
                collect_selected_capabilities(item)

    def collect_temporal(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "temporal_scope" and isinstance(item, dict):
                    bounded = {
                        field: item.get(field)
                        for field in (
                            "mode",
                            "reference_time_iso",
                            "start_time_iso",
                            "end_time_iso",
                            "granularity",
                            "aggregation",
                        )
                        if item.get(field) is not None
                    }
                    if bounded:
                        temporal_evidence["requested_scope"] = bounded
                elif key in {
                    "reference_time_iso",
                    "start_time_iso",
                    "end_time_iso",
                    "observation_time",
                    "effective_time",
                    "provider_time",
                    "selected_time",
                    "default_time",
                    "provider_default_time",
                    "layer_time",
                } and isinstance(item, (bool, int, float, str)):
                    temporal_evidence.setdefault(key, item)
                collect_temporal(item)
        elif isinstance(value, list):
            for item in value:
                collect_temporal(item)

    def collect_operational(value: Any) -> None:
        nonlocal iteration_count, model_call_count, tool_call_count
        nonlocal state_transition_count
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {"model_calls", "model_call_count"}:
                    model_call_count = max(model_call_count, _safe_trace_int(item))
                elif key in {"tool_calls", "tool_call_count"}:
                    tool_call_count = max(tool_call_count, _safe_trace_int(item))
                elif key in {"transitions", "state_transitions", "state_transition_count"}:
                    state_transition_count = max(
                        state_transition_count, _safe_trace_int(item)
                    )
                elif key in {"current_iteration", "iteration"}:
                    iteration_count = max(iteration_count, _safe_trace_int(item))
                elif key == "exposure_trace" and isinstance(item, list):
                    for exposure in item:
                        if not isinstance(exposure, dict):
                            continue
                        tool_name = exposure.get("tool") or exposure.get("tool_name")
                        if not isinstance(tool_name, str) or not tool_name.strip():
                            continue
                        iteration = exposure.get("iteration")
                        iteration_key = (
                            str(_safe_trace_int(iteration))
                            if isinstance(iteration, (int, str))
                            else "unknown"
                        )
                        exposed_by_iteration.setdefault(iteration_key, [])
                        add_unique(exposed_by_iteration[iteration_key], tool_name)
                collect_operational(item)
        elif isinstance(value, list):
            for item in value:
                collect_operational(item)

    for event in safe_events:
        kind = str(event.get("kind") or event.get("type") or "")
        iteration = event.get("iteration")
        if isinstance(iteration, int):
            iteration_count = max(iteration_count, iteration)
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        collect_safe_ids(payload)
        collect_safe_ids(event.get("evidence_refs"))
        if kind in {"tool_selected", "tool_result", "map_prepared"}:
            collect_selected_capabilities(payload)
        collect_temporal(payload)
        collect_operational(event)
        if kind == "tool_selected":
            tool_name = event.get("tool_name") or payload.get("tool_name")
            add_unique(selected_tools, tool_name)
            if isinstance(iteration, int) and isinstance(tool_name, str):
                exposed_by_iteration.setdefault(str(iteration), [])
                add_unique(exposed_by_iteration[str(iteration)], tool_name)
            if tool_name == "apply_map_plan":
                apply_map_plan_attempts += 1
        elif kind == "tool_result":
            tool_name = event.get("tool_name") or payload.get("tool_name")
            status = event.get("status") or payload.get("status")
            tool_results.append(
                {
                    "tool": tool_name,
                    "status": status,
                    "iteration": iteration,
                    "error_type": (
                        payload.get("error", {}).get("error_type")
                        if isinstance(payload.get("error"), dict)
                        else None
                    ),
                }
            )
        elif kind in {"completion", "completion_decision", "run_suspended"}:
            terminal_reason = (
                payload.get("completion_reason")
                or payload.get("reason")
                or payload.get("stopped_reason")
                or terminal_reason
            )
        if kind in {"checkpoint", "completion_decision", "render_observed", "stage"}:
            render_payload = (
                payload.get("payload")
                if isinstance(payload.get("payload"), dict)
                else payload
            )
            render_checks = render_payload.get("checks")
            render_preparation.append(
                {
                    "kind": kind,
                    "iteration": iteration,
                    "render_verified": payload.get("render_verified"),
                    "render_status": (
                        render_payload.get("status")
                        if isinstance(render_payload, dict)
                        else None
                    ),
                    "render_checks": (
                        {
                            key: bool(render_checks.get(key))
                            for key in (
                                "required_sources_loaded",
                                "required_layers_present",
                                "viewport_valid",
                            )
                            if key in render_checks
                        }
                        if isinstance(render_checks, dict)
                        else None
                    ),
                    "prepared_map": bool(
                        payload.get("prepared_map_session")
                        or payload.get("prepared_map")
                        or (
                            isinstance(payload.get("run_state"), dict)
                            and payload["run_state"].get("prepared_map_session")
                        )
                    ),
                }
            )
        run_state = payload.get("run_state")
        if isinstance(run_state, dict):
            model_call_count = max(
                model_call_count, _safe_trace_int(run_state.get("model_calls"))
            )
            state_transition_count = max(
                state_transition_count,
                _safe_trace_int(run_state.get("transitions")),
            )
            if isinstance(run_state.get("route"), dict):
                collect_safe_ids({"route": run_state["route"]})
            if run_state.get("termination_reason"):
                terminal_reason = run_state["termination_reason"]
            collect_temporal(run_state)

    return {
        "status": "ok",
        "conversation_id": conversation_id,
        "run_id": run_id,
        "run_version": run_version,
        "resolved_route": route,
        "selected_capability_ids": capability_ids[:32],
        "iteration_count": iteration_count,
        "model_call_count": model_call_count,
        "tool_call_count": max(
            tool_call_count,
            len([item for item in safe_events if item.get("kind") == "tool_selected"]),
        ),
        "state_transition_count": state_transition_count,
        "terminal_or_stopped_reason": terminal_reason,
        "exposed_tools_by_iteration": exposed_by_iteration,
        "selected_tool_names": selected_tools,
        "tool_result_statuses": tool_results[:64],
        "evidence_references": evidence_refs[:32],
        "apply_map_plan_attempts": apply_map_plan_attempts,
        "render_preparation": render_preparation[-16:],
        "temporal_evidence": temporal_evidence,
    }


def _expand_overlay_controls(page: Page) -> None:
    toggle = page.locator(".overlay-controls__toggle")
    if not toggle.count():
        return
    if toggle.get_attribute("aria-expanded") != "true":
        toggle.click()
        page.wait_for_timeout(500)


def _map_evidence(page: Page, expected_capability_id: str | None) -> dict[str, Any]:
    if not expected_capability_id:
        return {
            "source_state": "unobserved",
            "layer_state": "unobserved",
            "visible_raster_pixels": "unobserved",
            "render_ack": "unobserved",
        }
    hints = TARGET_LABEL_HINTS.get(
        expected_capability_id,
        (expected_capability_id,),
    )
    hints = tuple(hint.casefold() for hint in hints)
    _expand_overlay_controls(page)
    target_status: str | None = None
    target_visible: bool | None = None
    rows = page.locator(".overlay-control-row")
    for index in range(rows.count()):
        row = rows.nth(index)
        row_text = (row.inner_text() or "").casefold()
        if not any(hint in row_text for hint in hints):
            continue
        label = row.locator("label").first
        target_status = label.get_attribute("data-render-status")
        checkbox = row.locator("input[type='checkbox']")
        target_visible = checkbox.is_checked() if checkbox.count() else None
        break
    canvas_count = page.locator(".maplibregl-canvas").count()
    attribution = page.locator(".attribution-panel")
    return {
        "source_state": (
            "target_overlay_status_loaded"
            if target_status == "loaded"
            else target_status or "unobserved"
        ),
        "layer_state": (
            "visible_and_loaded"
            if target_status == "loaded" and target_visible
            else target_status or "unobserved"
        ),
        "visible_raster_pixels": (
            "canvas_present_target_loaded"
            if canvas_count > 0 and target_status == "loaded" and target_visible
            else "unobserved"
        ),
        "attribution": {
            "present": attribution.count() > 0,
            "text": _bounded_text(attribution.inner_text()) if attribution.count() else "",
        },
        "render_ack": "unobserved",
    }


def _scenario_result(
    page: Page,
    capture: _RasterCapture,
    scenario_id: str,
    prompt: str,
    screenshot: Path,
    expected_capability_id: str | None = None,
    run_trace: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body_text = _bounded_text(page.locator("body").inner_text())
    proxy_events = [
        event for event in capture.events if event.get("transport") == "aegis_proxy"
    ]
    target_proxy_events = [
        event
        for event in proxy_events
        if expected_capability_id is None
        or event.get("capability_id") == expected_capability_id
    ]
    target_proxy_responses = [
        event for event in target_proxy_events if event.get("kind") == "response"
    ]
    target_proxy_failures = [
        event for event in target_proxy_events if event.get("kind") == "requestfailed"
    ]
    direct_upstream_events = [
        event
        for event in capture.events
        if event.get("transport") == "direct_upstream"
    ]
    target_image_responses = [
        event
        for event in target_proxy_responses
        if int(event.get("status") or 0) == 200
        and str(event.get("content_type") or "").lower().startswith("image/")
    ]
    map_evidence = _map_evidence(page, expected_capability_id)
    if run_trace:
        render_preparation = run_trace.get("render_preparation", [])
        if any(
            item.get("kind") == "render_observed"
            and item.get("render_status") in {"ready", "verified"}
            for item in render_preparation
        ):
            map_evidence["render_ack"] = "render_observed"
        elif any(
            item.get("kind") == "render_observed"
            for item in render_preparation
        ):
            map_evidence["render_ack"] = "render_failed"
        elif any(item.get("render_verified") is True for item in render_preparation):
            map_evidence["render_ack"] = "verified_in_trace"
    proxy_time_parameters: list[dict[str, Any]] = []
    time_keys = {
        "time",
        "date",
        "start",
        "end",
        "start_time",
        "end_time",
    }
    for event in target_proxy_events:
        if event.get("kind") not in {"request", "response"}:
            continue
        parsed = urlsplit(str(event.get("url") or ""))
        values = {
            key: value
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if key.casefold() in time_keys
        }
        if values:
            proxy_time_parameters.append(
                {"kind": event.get("kind"), "parameters": values}
            )
    if not page.locator(".chat-message--assistant").count():
        classification = "route_failure"
    elif not target_proxy_events:
        classification = "proxy_route_failure"
    elif target_proxy_failures or not target_proxy_responses:
        classification = "upstream_request_failure"
    elif not target_image_responses:
        classification = "invalid_image_payload"
    elif "render_ack" in body_text.casefold() or "render failed" in body_text.casefold():
        classification = "acknowledgement_or_maplibre_failure"
    elif (
        map_evidence["source_state"] == "target_overlay_status_loaded"
        and map_evidence["layer_state"] == "visible_and_loaded"
        and map_evidence["visible_raster_pixels"] != "unobserved"
        and map_evidence["attribution"]["present"]
        and map_evidence["render_ack"] in {"render_observed", "verified_in_trace"}
    ):
        classification = "raster_render_pass"
    else:
        classification = "maplibre_pixels_and_ack_unobserved"
    return {
        "scenario_id": scenario_id,
        "prompt": prompt,
        "assistant_response_visible": page.locator(".chat-message--assistant").count()
        > 0,
        "maplibre_map_count": page.locator(".maplibregl-map").count(),
        "maplibre_canvas_count": page.locator(".maplibregl-canvas").count(),
        "ui_text": body_text,
        "raster_events": capture.events,
        "console": capture.console,
        "page_errors": capture.page_errors,
        "classification": classification,
        "expected_capability_id": expected_capability_id,
        "proxy_capabilities_seen": sorted(
            {
                str(event.get("capability_id"))
                for event in proxy_events
                if event.get("capability_id")
            }
        ),
        "proxy_request_count": len(
            [event for event in target_proxy_events if event.get("kind") == "request"]
        ),
        "proxy_response_statuses": [event.get("status") for event in target_proxy_responses],
        "proxy_response_content_types": [
            event.get("content_type") for event in target_proxy_responses
        ],
        "target_image_response_count": len(target_image_responses),
        "direct_upstream_browser_request_count": len(
            [event for event in direct_upstream_events if event.get("kind") == "request"]
        ),
        "map_evidence": map_evidence,
        "temporal_evidence": {
            "trace": (
                run_trace.get("temporal_evidence", {})
                if isinstance(run_trace, dict)
                else {}
            ),
            "proxy_time_parameters": proxy_time_parameters,
        },
        "run_trace": run_trace or {"status": "unavailable"},
        "screenshot": str(screenshot),
    }


def test_live_public_raster_request_diagnostics(
    page: Page,
    base_url: str,
    api_base_url: str,
    artifact_root: Path,
    read_backend_log_tail,
) -> None:
    """Persist exact public-raster network evidence without changing map gates."""

    dirs = ensure_test_artifact_dirs(artifact_root, TEST_ID)
    preflight = _provider_probe(page, api_base_url)
    ready = (
        preflight["http_status"] == 200
        and preflight["status"] == "passed"
        and preflight["parse_status"] == "complete"
        and preflight["provider"] == "opencode-go"
        and preflight["model"] == "deepseek-v4.1-flash"
    )
    if not ready:
        (dirs["reports"] / f"{TEST_ID}.json").write_text(
            json.dumps({"provider_probe": preflight}, indent=2), encoding="utf-8"
        )
        pytest.skip(f"Exact live provider lane was not ready: {preflight}")

    results: list[dict[str, Any]] = []
    for scenario_id, prompt in SCENARIOS:
        page.goto(base_url)
        page.get_by_role("button", name="Start new chat").click()
        expect(page.locator(".chat-message--assistant")).to_have_count(0)
        capture = _RasterCapture()
        capture.attach(page)
        page.get_by_label("Chat message").fill(prompt)
        page.get_by_role("button", name="Send message").click()
        expect(page.get_by_text(prompt, exact=True)).to_be_visible(timeout=15_000)
        expect(page.locator(".chat-message--assistant").last).to_be_visible(
            timeout=90_000
        )
        stop_button = page.get_by_role("button", name="Stop generating")
        if stop_button.count():
            expect(stop_button).not_to_be_visible(timeout=90_000)
        page.wait_for_timeout(5_000)
        _expand_overlay_controls(page)
        screenshot = write_snapshot(page, dirs["screenshots"], scenario_id)
        conversation_id = _read_conversation_id(page)
        run_trace = _read_latest_run_trace(page, api_base_url, conversation_id)
        result = _scenario_result(
            page,
            capture,
            scenario_id,
            prompt,
            screenshot,
            expected_capability_id=SCENARIO_CAPABILITIES.get(scenario_id),
            run_trace=run_trace,
        )
        backend_tail = read_backend_log_tail(500)
        raster_diagnostics = [
            line
            for line in backend_tail.splitlines()
            if "geospatial_tile_proxy" in line
        ][-64:]
        result["backend_raster_diagnostics"] = raster_diagnostics
        write_log_tail(
            dirs["logs"],
            f"{TEST_ID}-{scenario_id}",
            "\n".join(raster_diagnostics),
        )
        results.append(result)
        (dirs["http"] / f"{scenario_id}.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    report = {
        "test_id": TEST_ID,
        "provider_probe": preflight,
        "scenarios": results,
        "artifacts": {
            "screenshots": str(dirs["screenshots"]),
            "network": str(dirs["http"]),
        },
        "tested_commit": os.environ.get("APP_TEST_COMMIT", "unknown"),
    }
    (dirs["reports"] / f"{TEST_ID}.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
