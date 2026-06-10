from __future__ import annotations

import json
import re
import time
from typing import Any

from playwright.sync_api import Page, Route, expect

from tests.e2e.helpers.chat_stub_payloads import (
    chat_turn_clarification_response,
    chat_turn_map_response,
    model_settings_payload,
)


###############################################################################
def _json_ok(route: Route, payload: dict[str, Any]) -> None:
    route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))


###############################################################################
def _stub_ui_api(page: Page) -> None:
    state = {"session_id": 777}

    def handle_turn(route: Route) -> None:
        body = route.request.post_data_json
        message = str(body.get("message") or "")
        session_id = int(body.get("session_id") or state["session_id"])
        if "ambiguous" in message.lower() or "weather only" in message.lower():
            payload = chat_turn_clarification_response(
                session_id, "Please clarify location and time."
            )
        else:
            payload = chat_turn_map_response(
                session_id, "Search executed successfully."
            )
        state["session_id"] = payload["session_id"]
        _json_ok(route, payload)

    page.route(re.compile(r".*/api/chat/turn$"), handle_turn)
    page.route(
        re.compile(r".*/api/chat/settings$"),
        lambda route: _json_ok(route, model_settings_payload()),
    )
    page.route(
        re.compile(r".*/api/chat/models$"),
        lambda route: _json_ok(
            route,
            {
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
            },
        ),
    )


###############################################################################
def test_25_sequential_turns_mixed_with_new_chat_resets(
    page: Page, base_url: str
) -> None:
    _stub_ui_api(page)
    page.goto(base_url)
    composer = page.get_by_label("Chat message")
    for idx in range(25):
        text = "ambiguous weather only" if idx % 7 == 0 else f"show map turn {idx}"
        composer.fill(text)
        page.get_by_role("button", name="Send").click()
        expect(page.locator(".chat-message--assistant").last).to_be_visible(timeout=15000)
        if idx in {9, 18}:
            page.get_by_role("button", name="Start new chat").click()
            expect(page.get_by_text("Map Workspace")).to_be_visible()
    expect(page.get_by_label("Chat message")).to_be_visible()


###############################################################################
def test_rapid_double_submit_does_not_duplicate_assistant_state(
    page: Page, base_url: str
) -> None:
    _stub_ui_api(page)

    def delayed_turn(route: Route) -> None:
        time.sleep(0.15)
        _json_ok(route, chat_turn_map_response(999, "Search executed successfully."))

    page.route(re.compile(r".*/api/chat/turn$"), delayed_turn)
    page.goto(base_url)
    page.get_by_label("Chat message").fill("show map quickly")
    send = page.get_by_role("button", name="Send")
    send.click()
    if send.is_enabled():
        send.click()
    expect(page.locator(".chat-message--assistant")).to_have_count(1, timeout=10000)


###############################################################################
def test_repeated_refresh_loop_preserves_state(page: Page, base_url: str) -> None:
    _stub_ui_api(page)
    page.goto(base_url)
    page.get_by_label("Chat message").fill("show map for refresh loop")
    page.get_by_role("button", name="Send").click()
    expect(page.locator(".chat-message--assistant").last).to_be_visible(timeout=15000)
    for _ in range(10):
        page.reload()
        expect(page.get_by_text("show map for refresh loop")).to_be_visible()
        expect(page.locator(".chat-message").first).to_be_visible()


###############################################################################
def test_route_switching_20_cycles_preserves_query_and_chat_state(
    page: Page, base_url: str
) -> None:
    _stub_ui_api(page)
    page.goto(base_url)
    page.get_by_label("Chat message").fill("show map state before route cycles")
    page.get_by_role("button", name="Send").click()
    expect(page.locator(".chat-message--assistant").first).to_be_visible(timeout=15000)

    for _ in range(20):
        page.get_by_role("link", name="Model Settings").click()
        expect(page).to_have_url(re.compile(r".*/settings"))
        page.get_by_placeholder("Search models").fill("gpt")
        page.get_by_role("link", name="Search").click()
        expect(page).to_have_url(re.compile(rf"{re.escape(base_url.rstrip('/'))}/?$"))
        expect(page.get_by_text("show map state before route cycles")).to_be_visible()

    page.get_by_role("link", name="Model Settings").click()
    expect(page.get_by_placeholder("Search models")).to_have_value("gpt")


###############################################################################
def test_large_composer_input_does_not_freeze_ui(page: Page, base_url: str) -> None:
    _stub_ui_api(page)
    page.goto(base_url)
    large_text = "Rome overlay " * 1200
    page.get_by_label("Chat message").fill(large_text)
    page.get_by_role("button", name="Send").click()
    expect(page.locator(".chat-message--assistant").last).to_be_visible(timeout=15000)
    expect(page.get_by_label("Chat message")).to_be_visible()


###############################################################################
def test_overlay_toggle_and_opacity_restore_after_refresh(
    page: Page, base_url: str
) -> None:
    _stub_ui_api(page)
    page.goto(base_url)
    page.get_by_label("Chat message").fill("show map with overlays")
    page.get_by_role("button", name="Send").click()
    expect(page.locator(".chat-message--assistant").last).to_be_visible(timeout=15000)
    expect(page.locator(".overlay-controls")).to_be_visible(timeout=15000)

    first_checkbox = page.locator(".overlay-control-row input[type='checkbox']").first
    first_checkbox.uncheck()
    first_range = page.locator(".overlay-control-row input[type='range']").first
    first_range.evaluate(
        "(node) => { node.value = '25'; node.dispatchEvent(new Event('input', { bubbles: true })); }"
    )
    page.reload()
    expect(page.locator(".overlay-controls")).to_be_visible()
    expect(
        page.locator(".overlay-control-row input[type='checkbox']").first
    ).not_to_be_checked()
    restored = page.locator(
        ".overlay-control-row input[type='range']"
    ).first.input_value()
    assert int(restored) == 25
