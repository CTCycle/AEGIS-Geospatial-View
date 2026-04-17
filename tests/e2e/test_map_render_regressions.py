from __future__ import annotations

import base64
import json
import re
from collections.abc import Callable
from typing import Any

from playwright.sync_api import ConsoleMessage, Page, Route, expect

from tests.e2e.helpers.chat_stub_payloads import model_settings_payload

PNG_1X1_TRANSPARENT = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Jte8AAAAASUVORK5CYII="
)


def _json_ok(route: Route, payload: dict[str, Any]) -> None:
    route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))


def _models_payload() -> dict[str, Any]:
    return {
        "cloud": [
            {
                "id": "gpt-4.1-mini",
                "name": "gpt-4.1-mini",
                "description": "Cloud model",
                "provider": "openai",
                "capabilities": ["chat"],
                "metadata": {},
            }
        ],
        "local": [],
    }


def _turn_payload() -> dict[str, Any]:
    return {
        "session_id": 7001,
        "assistant_message": "Search executed successfully.",
        "structured_intent": {"request_text": "show map at 41.9028, 12.4964"},
        "extracted_state": {"location": {"city": "Rome", "country": "Italy"}},
        "map_session": {
            "center": {"latitude": 41.9028, "longitude": 12.4964},
            "bounds": [12.4963044, 41.902725, 12.4964044, 41.902825],
            "basemap": {
                "id": "osm_default",
                "label": "OpenStreetMap",
                "provider": "osm",
                "type": "tile",
                "tile_url": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
                "requires_key": False,
            },
            "overlays": [],
            "compliance_warnings": [],
        },
        "tool_payload": {"execution": "map_search", "selected_overlay_ids": []},
        "follow_up_required": False,
        "fallback_mode": "none",
    }


def _setup_stubs(page: Page, record_tile_zoom: Callable[[int], None]) -> None:
    page.route(re.compile(r".*/api/chat/turn$"), lambda route: _json_ok(route, _turn_payload()))
    page.route(re.compile(r".*/api/chat/settings$"), lambda route: _json_ok(route, model_settings_payload()))
    page.route(re.compile(r".*/api/chat/models$"), lambda route: _json_ok(route, _models_payload()))
    page.route(
        re.compile(r".*/api/maps/catalog$"),
        lambda route: _json_ok(route, {"providers": [], "basemaps": [], "overlays": []}),
    )

    def handle_osm_proxy(route: Route) -> None:
        match = re.search(r"/api/maps/basemaps/osm/(\d+)/\d+/\d+\.png$", route.request.url)
        if match:
            record_tile_zoom(int(match.group(1)))
        route.fulfill(status=200, content_type="image/png", body=PNG_1X1_TRANSPARENT)

    page.route(re.compile(r".*/api/maps/basemaps/osm/\d+/\d+/\d+\.png$"), handle_osm_proxy)


def _collect_console_errors(page: Page) -> list[str]:
    errors: list[str] = []

    def capture(message: ConsoleMessage) -> None:
        if message.type == "error":
            errors.append(message.text)

    page.on("console", capture)
    return errors


def _assert_no_render_blockers(errors: list[str]) -> None:
    blockers = [
        line
        for line in errors
        if any(
            token in line.lower()
            for token in ("maplibre", "cors", "tile", "webgl", "render", "failed to load")
        )
    ]
    assert not blockers, f"Render-blocking console errors detected: {blockers}"


def test_chat_success_immediately_mounts_map_and_limits_tile_zoom(page: Page, base_url: str) -> None:
    requested_zooms: list[int] = []
    _setup_stubs(page, requested_zooms.append)
    errors = _collect_console_errors(page)

    page.goto(base_url)
    page.get_by_label("Chat message").fill("show map at 41.9028, 12.4964")
    page.get_by_role("button", name="Send").click()

    expect(page.get_by_text("Search executed successfully.")).to_be_visible()
    expect(page.locator(".maplibregl-canvas")).to_be_visible()
    assert requested_zooms, "Expected raster tile requests for map rendering"
    assert max(requested_zooms) <= 18
    _assert_no_render_blockers(errors)


def test_refresh_restores_rendered_map_without_console_errors(page: Page, base_url: str) -> None:
    requested_zooms: list[int] = []
    _setup_stubs(page, requested_zooms.append)
    errors = _collect_console_errors(page)

    page.goto(base_url)
    page.get_by_label("Chat message").fill("show map at 41.9028, 12.4964")
    page.get_by_role("button", name="Send").click()
    expect(page.locator(".maplibregl-canvas")).to_be_visible()

    page.reload()

    expect(page.get_by_text("show map at 41.9028, 12.4964")).to_be_visible()
    expect(page.get_by_text("Search executed successfully.")).to_be_visible()
    expect(page.locator(".maplibregl-canvas")).to_be_visible()
    assert requested_zooms, "Expected raster tile requests for initial or restored map render"
    _assert_no_render_blockers(errors)
