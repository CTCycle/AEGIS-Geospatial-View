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
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import pytest
from playwright.sync_api import ConsoleMessage, Page, expect

from tests.e2e.helpers.artifacts import ensure_test_artifact_dirs, write_snapshot


TEST_ID = "RASTER-LIVE-DIAGNOSTICS"
MAX_EVENTS = 512
MAX_TEXT = 8000
RASTER_HOSTS = {
    "hazards.fema.gov",
    "services.terrascope.be",
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


def _request_failure(request: Any) -> str | None:
    failure = getattr(request, "failure", None)
    if callable(failure):
        failure = failure()
    if isinstance(failure, dict):
        return _bounded_text(str(failure.get("errorText") or failure))
    if failure is not None:
        return _bounded_text(str(failure))
    return None


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


def _scenario_result(
    page: Page,
    capture: _RasterCapture,
    scenario_id: str,
    prompt: str,
    screenshot: Path,
) -> dict[str, Any]:
    body_text = _bounded_text(page.locator("body").inner_text())
    proxy_events = [
        event for event in capture.events if event.get("transport") == "aegis_proxy"
    ]
    proxy_responses = [
        event for event in proxy_events if event.get("kind") == "response"
    ]
    proxy_failures = [
        event for event in proxy_events if event.get("kind") == "requestfailed"
    ]
    if not page.locator(".chat-message--assistant").count():
        classification = "route_failure"
    elif not proxy_events:
        classification = "proxy_route_failure"
    elif proxy_failures or not proxy_responses:
        classification = "upstream_request_failure"
    elif any(
        not str(event.get("content_type") or "").lower().startswith("image/")
        or int(event.get("status") or 0) >= 400
        for event in proxy_responses
    ):
        classification = "invalid_image_payload"
    elif "render_ack" in body_text.casefold() or "render failed" in body_text.casefold():
        classification = "acknowledgement_or_maplibre_failure"
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
        "proxy_request_count": len(
            [event for event in proxy_events if event.get("kind") == "request"]
        ),
        "proxy_response_statuses": [event.get("status") for event in proxy_responses],
        "map_evidence": {
            "source_state": "unobserved",
            "layer_state": "unobserved",
            "visible_raster_pixels": "unobserved",
            "render_ack": "unobserved",
        },
        "screenshot": str(screenshot),
    }


def test_live_public_raster_request_diagnostics(
    page: Page,
    base_url: str,
    api_base_url: str,
    artifact_root: Path,
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
        screenshot = write_snapshot(page, dirs["screenshots"], scenario_id)
        result = _scenario_result(page, capture, scenario_id, prompt, screenshot)
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
