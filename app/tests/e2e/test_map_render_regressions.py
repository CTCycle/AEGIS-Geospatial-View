from __future__ import annotations

import base64
import json
import re
from collections.abc import Callable
from typing import Any

from playwright.sync_api import ConsoleMessage, Page, Route, expect

from tests.e2e.helpers.chat_stub_payloads import (
    chat_completion_map_payload,
    conversation_snapshot_payload,
    geospatial_catalog_payload,
    model_settings_payload,
)
from tests.e2e.helpers.realtime_stub import register_realtime_stub

PNG_1X1_TRANSPARENT = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGBgAAAABQABpfZFQAAAAABJRU5ErkJggg=="
)


###############################################################################
def _json_ok(route: Route, payload: dict[str, Any]) -> None:
    route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))


###############################################################################
def _models_payload() -> dict[str, Any]:
    return {
        "cloud": [
            {
                "id": "gpt-4.1-mini",
                "name": "gpt-4.1-mini",
                "description": "Cloud model",
                "provider": "openai",
                "capabilities": ["chat"],
                "tool_support_source": "fixture",
                "context_profile_source": "fixture",
                "metadata": {},
            }
        ],
        "local": [],
        "sources": {},
    }


###############################################################################
def _turn_payload() -> dict[str, Any]:
    payload = chat_completion_map_payload(7001, "Search executed successfully.")
    payload["map_session"]["bounds"] = [12.4963044, 41.902725, 12.4964044, 41.902825]
    payload["map_session"]["overlay_collection"]["instances"] = []
    payload["tool_payload"] = {"execution": "map_search", "selected_overlay_ids": []}
    return payload


###############################################################################
def _setup_stubs(page: Page, record_tile_zoom: Callable[[int], None]) -> None:
    register_realtime_stub(page, lambda _message, _run_number: _turn_payload())
    page.route(
        re.compile(r".*/api/chat/settings$"),
        lambda route: _json_ok(route, model_settings_payload()),
    )
    page.route(
        re.compile(r".*/api/chat/models$"),
        lambda route: _json_ok(route, _models_payload()),
    )
    page.route(
        re.compile(r".*/api/geospatial/capabilities$"),
        lambda route: _json_ok(route, geospatial_catalog_payload()),
    )
    page.route(
        re.compile(r".*/api/conversations/[^/]+$"),
        lambda route: _json_ok(route, conversation_snapshot_payload()),
    )
    page.route(
        re.compile(r".*/api/conversations$"),
        lambda route: _json_ok(
            route, {"conversation_id": "conversation-e2e", "title": "E2E"}
        ),
    )

    def handle_osm_proxy(route: Route) -> None:
        match = re.search(
            r"/api/geospatial/tiles/osm_default/(\d+)/\d+/\d+\.png(?:\?.*)?$",
            route.request.url,
        )
        if match:
            record_tile_zoom(int(match.group(1)))
        route.fulfill(status=200, content_type="image/png", body=PNG_1X1_TRANSPARENT)

    page.route("**/api/geospatial/tiles/osm_default/**", handle_osm_proxy)


###############################################################################
def _collect_console_errors(page: Page) -> list[str]:
    errors: list[str] = []

    def capture(message: ConsoleMessage) -> None:
        if message.type == "error":
            errors.append(message.text)

    page.on("console", capture)
    return errors


###############################################################################
def _assert_no_render_blockers(errors: list[str]) -> None:
    blockers = [
        line
        for line in errors
        if any(
            token in line.lower()
            for token in (
                "cors",
                "webgl",
                "context lost",
            )
        )
    ]
    assert not blockers, f"Render-blocking console errors detected: {blockers}"


###############################################################################
def _assert_map_uses_full_canvas(page: Page) -> None:
    """Verify the rendered map and MapLibre canvas share the full map frame."""
    boxes = {
        "canvas panel": page.locator(".canvas-panel__body").bounding_box(),
        "map preview host": page.locator("app-map-preview").bounding_box(),
        "map frame": page.locator(".maplibre-wrap:visible").bounding_box(),
        "map container": page.locator(".maplibre-container:visible").last.bounding_box(),
        "map canvas": page.locator(".maplibregl-canvas:visible").last.bounding_box(),
    }
    missing = [name for name, box in boxes.items() if box is None]
    assert not missing, f"Missing map geometry for: {missing}"

    panel = boxes["canvas panel"]
    assert panel is not None
    for name in ("map preview host", "map frame", "map container", "map canvas"):
        box = boxes[name]
        assert box is not None
        assert abs(box["x"] - panel["x"]) <= 2, f"{name} is not aligned to the canvas"
        assert abs(box["y"] - panel["y"]) <= 2, f"{name} is not aligned to the canvas"
        assert abs(
            (box["x"] + box["width"]) - (panel["x"] + panel["width"])
        ) <= 2, f"{name} does not use the full canvas width"
        assert abs(
            (box["y"] + box["height"]) - (panel["y"] + panel["height"])
        ) <= 2, f"{name} does not use the full canvas height"


###############################################################################
def test_chat_success_immediately_mounts_map_and_limits_tile_zoom(
    page: Page, base_url: str
) -> None:
    requested_zooms: list[int] = []
    _setup_stubs(page, requested_zooms.append)
    errors = _collect_console_errors(page)

    page.goto(base_url)
    page.get_by_label("Chat message").fill("show map at 41.9028, 12.4964")
    page.get_by_role("button", name="Send message").click()

    expect(page.locator(".chat-message--assistant").last).to_be_visible(timeout=15000)
    expect(page.locator(".maplibregl-canvas")).to_be_visible(timeout=15000)
    page.wait_for_timeout(500)
    _assert_map_uses_full_canvas(page)
    assert requested_zooms, "Expected raster tile requests for map rendering"
    assert max(requested_zooms) <= 19
    _assert_no_render_blockers(errors)


###############################################################################
def test_refresh_restores_rendered_map_without_console_errors(
    page: Page, base_url: str
) -> None:
    requested_zooms: list[int] = []
    _setup_stubs(page, requested_zooms.append)
    errors = _collect_console_errors(page)

    page.goto(base_url)
    page.get_by_label("Chat message").fill("show map at 41.9028, 12.4964")
    page.get_by_role("button", name="Send message").click()
    expect(page.locator(".maplibregl-canvas")).to_be_visible(timeout=15000)
    page.wait_for_timeout(500)

    page.reload()

    expect(page.get_by_text("show map at 41.9028, 12.4964")).to_be_visible()
    expect(page.get_by_text("Search executed successfully.")).to_be_visible()
    expect(page.locator(".maplibregl-canvas")).to_be_visible()
    assert requested_zooms, (
        "Expected raster tile requests for initial or restored map render"
    )
    _assert_no_render_blockers(errors)
