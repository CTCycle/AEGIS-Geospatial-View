"""Capture request-level evidence for the Tier 3 route-matrix live rows.

Covers the ISSUE-006 / ROUTE-LIVE natural-language rows (Census demographics,
Open-Meteo aliases, Acropolis semantics, imagery extent, weather budget,
generic-infrastructure clarification) and the EEA public-raster render retry
(RASTER-LIVE / GEO-FOCUS-16). Each scenario records the run trace, selected
capabilities, model/tool call counts, browser map state, and network evidence;
the persisted UI outcome is the acceptance authority and provider failures are
kept separate from routing/renderer outcomes.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

import pytest
from playwright.sync_api import ConsoleMessage, Page, expect

from tests.e2e.helpers.artifacts import (
    ensure_test_artifact_dirs,
    write_log_tail,
    write_snapshot,
)
from tests.e2e.test_live_raster_diagnostics import (
    _bounded_text,
    _provider_probe,
    _read_conversation_id,
    _read_latest_run_trace,
    _sanitize_url,
)

TEST_ID = "ROUTE-MATRIX-LIVE"
MAX_EVENTS = 512
ROUTE_UPSTREAM_HOSTS = {
    "tigerweb.geo.census.gov",
    "api.census.gov",
    "api.open-meteo.com",
    "nominatim.openstreetmap.org",
    "overpass-api.de",
    "noise.discomap.eea.europa.eu",
    "services.terrascope.be",
    "mapproxy.terrascope.be",
    "titiler.terrascope.be",
    "hazards.fema.gov",
    "gibs.earthdata.nasa.gov",
    "server.arcgisonline.com",
}
# Scenario id -> (prompt, expected_kind, expected_capability hint)
# expected_kind: "map" (browser map required), "text" (no map required),
# "clarification" (explicit assistant clarification, no provider execution).
SCENARIOS = (
    (
        "census_demographics_chicago",
        "Show census tracts around Chicago, Illinois.",
        "map",
        ("census", "tracts", "demographic"),
    ),
    (
        "openmeteo_alias_milan_air",
        "How is the air quality in Milan right now?",
        "text",
        ("air quality", "air-quality"),
    ),
    (
        "openmeteo_alias_oslo_weather",
        "Is it cold in Oslo right now?",
        "text",
        ("weather", "temperature"),
    ),
    (
        "openmeteo_alias_elevation",
        "What is the elevation of Rome, Italy?",
        "text",
        ("elevation", "terrain"),
    ),
    (
        "acropolis_athens",
        "Show me the Acropolis.",
        "map",
        (),
    ),
    (
        "imagery_extent_rome",
        "Show current satellite context for Rome, Italy.",
        "map",
        (),
    ),
    (
        "weather_budget_denver",
        "What will the weather be in Denver, Colorado tomorrow?",
        "text",
        ("weather", "forecast"),
    ),
    (
        "generic_infrastructure_rome",
        "Show infrastructure in Rome.",
        "clarification",
        (),
    ),
    (
        "eea_noise_milan",
        "Show noise exposure in Milan.",
        "map",
        ("noise", "eea"),
    ),
)


def _raster_transport(url: str) -> str | None:
    parsed = urlsplit(url)
    if parsed.path.startswith("/api/geospatial/tiles/"):
        return "aegis_proxy"
    if (parsed.hostname or "").casefold() in ROUTE_UPSTREAM_HOSTS:
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


class _RouteCapture:
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
                failure = getattr(request, "failure", None)
                if callable(failure):
                    failure = failure()
                if isinstance(failure, dict):
                    failure = str(failure.get("errorText") or failure)
                self._append(
                    {
                        "kind": "requestfailed",
                        "transport": transport,
                        "method": request.method,
                        "resource_type": request.resource_type,
                        "failure": _bounded_text(str(failure)) if failure else None,
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


def _expand_overlay_controls(page: Page) -> None:
    toggle = page.locator(".overlay-controls__toggle")
    if not toggle.count():
        return
    if toggle.get_attribute("aria-expanded") != "true":
        toggle.click()
        page.wait_for_timeout(500)


def _map_evidence(page: Page, hints: tuple[str, ...]) -> dict[str, Any]:
    map_count = page.locator(".maplibregl-map").count()
    canvas_count = page.locator(".maplibregl-canvas").count()
    attribution = page.locator(".attribution-panel")
    hints = tuple(hint.casefold() for hint in hints)
    target_status: str | None = None
    target_visible: bool | None = None
    overlay_rows: list[dict[str, str]] = []
    if map_count:
        _expand_overlay_controls(page)
        rows = page.locator(".overlay-control-row")
        for index in range(rows.count()):
            row = rows.nth(index)
            row_text = _bounded_text(row.inner_text() or "")
            overlay_rows.append({"index": index, "text": row_text[:400]})
            if hints and not any(hint in row_text.casefold() for hint in hints):
                continue
            label = row.locator("label").first
            target_status = label.get_attribute("data-render-status")
            checkbox = row.locator("input[type='checkbox']")
            target_visible = checkbox.is_checked() if checkbox.count() else None
    return {
        "maplibre_map_count": map_count,
        "maplibre_canvas_count": canvas_count,
        "attribution_present": attribution.count() > 0,
        "attribution_text": (
            _bounded_text(attribution.inner_text()) if attribution.count() else ""
        ),
        "target_overlay_status": target_status,
        "target_overlay_visible": target_visible,
        "overlay_rows": overlay_rows[:32],
    }


def _classify(
    scenario_id: str,
    expected_kind: str,
    body_text: str,
    map_evidence: dict[str, Any],
    run_trace: dict[str, Any],
    selected_capability_ids: list[str],
    direct_upstream_request_count: int,
) -> str:
    render_preparation = run_trace.get("render_preparation", []) or []
    ack_seen = any(
        item.get("kind") == "render_observed"
        and item.get("render_status") in {"ready", "verified"}
        for item in render_preparation
    )
    if expected_kind == "clarification":
        if "clarification" in body_text.casefold() or "which" in body_text.casefold():
            return "clarification_pass"
        return "clarification_not_observed"
    if expected_kind == "text":
        if map_evidence["maplibre_map_count"] > 0:
            return "unexpected_map_rendered"
        if selected_capability_ids or direct_upstream_request_count > 0:
            return "text_pass"
        return "text_no_provider_execution"
    if map_evidence["maplibre_map_count"] == 0:
        return "map_absent"
    if ack_seen:
        return "map_render_pass"
    if "render failed" in body_text.casefold() or "render" in body_text.casefold():
        return "map_render_failed"
    return "map_render_ack_unobserved"


def _scenario_result(
    page: Page,
    capture: _RouteCapture,
    scenario_id: str,
    prompt: str,
    expected_kind: str,
    hints: tuple[str, ...],
    screenshot: Path,
    run_trace: dict[str, Any],
) -> dict[str, Any]:
    body_text = _bounded_text(page.locator("body").inner_text())
    proxy_events = [
        event for event in capture.events if event.get("transport") == "aegis_proxy"
    ]
    direct_upstream_events = [
        event
        for event in capture.events
        if event.get("transport") == "direct_upstream"
    ]
    proxy_capabilities = sorted(
        {
            str(event.get("capability_id"))
            for event in proxy_events
            if event.get("capability_id")
        }
    )
    map_evidence = _map_evidence(page, hints)
    selected_capability_ids = run_trace.get("selected_capability_ids") or []
    classification = _classify(
        scenario_id,
        expected_kind,
        body_text,
        map_evidence,
        run_trace,
        selected_capability_ids,
        len(
            [
                event
                for event in direct_upstream_events
                if event.get("kind") == "request"
            ]
        ),
    )
    return {
        "scenario_id": scenario_id,
        "prompt": prompt,
        "expected_kind": expected_kind,
        "classification": classification,
        "assistant_response_visible": page.locator(".chat-message--assistant").count()
        > 0,
        "ui_text": body_text,
        "map_evidence": map_evidence,
        "network": {
            "proxy_request_count": len(
                [event for event in proxy_events if event.get("kind") == "request"]
            ),
            "proxy_response_statuses": [
                event.get("status")
                for event in proxy_events
                if event.get("kind") == "response"
            ],
            "proxy_capabilities_seen": proxy_capabilities,
            "direct_upstream_browser_request_count": len(
                [event for event in direct_upstream_events if event.get("kind") == "request"]
            ),
            "events": capture.events,
        },
        "console": capture.console,
        "page_errors": capture.page_errors,
        "run_trace": run_trace,
        "screenshot": str(screenshot),
    }


def test_route_matrix_live_diagnostics(
    page: Page,
    base_url: str,
    api_base_url: str,
    artifact_root: Path,
    read_backend_log_tail,
) -> None:
    """Persist exact-lane route-matrix and EEA raster evidence."""

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
    for scenario_id, prompt, expected_kind, hints in SCENARIOS:
        page.goto(base_url)
        page.get_by_role("button", name="Start new chat").click()
        expect(page.locator(".chat-message--assistant")).to_have_count(0)
        capture = _RouteCapture()
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
        page.wait_for_timeout(4_000)
        screenshot = write_snapshot(page, dirs["screenshots"], scenario_id)
        conversation_id = _read_conversation_id(page)
        run_trace = _read_latest_run_trace(page, api_base_url, conversation_id)
        result = _scenario_result(
            page,
            capture,
            scenario_id,
            prompt,
            expected_kind,
            hints,
            screenshot,
            run_trace,
        )
        backend_tail = read_backend_log_tail(500)
        routed_lines = [
            line
            for line in backend_tail.splitlines()
            if "geospatial_tile_proxy" in line or "route" in line
        ][-64:]
        result["backend_routed_diagnostics"] = routed_lines
        write_log_tail(
            dirs["logs"],
            f"{TEST_ID}-{scenario_id}",
            "\n".join(routed_lines),
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