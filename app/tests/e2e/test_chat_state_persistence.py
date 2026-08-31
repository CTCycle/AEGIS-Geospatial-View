from __future__ import annotations

import base64
import json
import re
import time
from typing import Any

from playwright.sync_api import Page, Route, expect

from tests.e2e.helpers.chat_stub_payloads import (
    conversation_snapshot_payload,
    geospatial_catalog_payload,
    model_settings_payload,
)


STORAGE_KEY = "aegis:webapp-ui-state:v1"
PNG_1X1_TRANSPARENT = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGBgAAAABQABpfZFQAAAAABJRU5ErkJggg=="
)


###############################################################################
def _json_ok(route: Route, payload: dict[str, Any]) -> None:
    route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))


###############################################################################
def _stub_settings_api(
    page: Page, *, include_conversation_snapshot: bool = True
) -> None:
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
                        "tool_support_source": "fixture",
                        "context_profile_source": "fixture",
                        "metadata": {},
                    }
                ],
                "local": [],
                "sources": {},
            },
        ),
    )
    page.route(
        re.compile(r".*/api/geospatial/capabilities$"),
        lambda route: _json_ok(route, geospatial_catalog_payload()),
    )
    page.route(
        "**/api/geospatial/tiles/osm_default/**",
        lambda route: route.fulfill(
            status=200, content_type="image/png", body=PNG_1X1_TRANSPARENT
        ),
    )
    page.route(
        "https://example.test/openaq/**",
        lambda route: route.fulfill(
            status=200, content_type="image/png", body=PNG_1X1_TRANSPARENT
        ),
    )
    if include_conversation_snapshot:
        page.route(
            re.compile(r".*/api/conversations/conversation-e2e$"),
            lambda route: _json_ok(route, conversation_snapshot_payload()),
        )
    else:
        page.route(
            re.compile(r".*/api/conversations/conversation-e2e$"),
            lambda route: route.fulfill(status=404, body="conversation not found"),
        )


###############################################################################
def _seed_persisted_state(page: Page, state: dict[str, Any]) -> None:
    payload_literal = json.dumps(state)
    storage_key_literal = json.dumps(STORAGE_KEY)
    page.add_init_script(
        f"""
        (() => {{
          const payload = {payload_literal};
          window.sessionStorage.setItem({storage_key_literal}, JSON.stringify(payload));
        }})();
        """
    )


###############################################################################
def _base_state(saved_at: int | None = None) -> dict[str, Any]:
    return {
        "version": 1,
        "savedAt": saved_at or int(time.time() * 1000),
        "chatPage": {
            "toolbarWidth": 520,
            "isToolbarCollapsed": False,
            "chatPanel": {
                "conversationId": "conversation-e2e",
                "lastRunSequence": 0,
                "composerDraft": "draft should persist",
                "transcriptScrollTop": 40,
            },
            "mapState": {
                "overlayVisibility": {"openaq_air_quality": True},
                "overlayOpacity": {"openaq_air_quality": 0.33},
            },
            "scrollY": 0,
        },
        "settingsPage": {
            "searchText": "gpt",
            "scrollY": 10,
            "modelGridScrollTop": 120,
        },
    }


###############################################################################
def test_refresh_same_tab_restores_chat_and_map_state(
    page: Page, base_url: str
) -> None:
    _stub_settings_api(page)
    _seed_persisted_state(page, _base_state())
    page.goto(base_url)
    expect(page.get_by_label("Chat message")).to_have_value("draft should persist")
    expect(page.get_by_text("show map at 41.9028, 12.4964")).to_be_visible()
    expect(page.locator(".maplibregl-canvas")).to_be_visible()


###############################################################################
def test_back_forward_between_routes_restores_both_states(
    page: Page, base_url: str
) -> None:
    _stub_settings_api(page)
    _seed_persisted_state(page, _base_state())
    page.goto(base_url)
    expect(page.get_by_text("show map at 41.9028, 12.4964")).to_be_visible()
    page.get_by_role("link", name="Model Settings").click()
    expect(page).to_have_url(re.compile(r".*/settings\?q=gpt"))
    expect(page.get_by_placeholder("Search models")).to_have_value("gpt")
    page.go_back()
    expect(page).to_have_url(re.compile(rf"{re.escape(base_url.rstrip('/'))}/?$"))
    expect(page.get_by_text("show map at 41.9028, 12.4964")).to_be_visible()
    page.go_forward()
    expect(page.get_by_placeholder("Search models")).to_have_value("gpt")


###############################################################################
def test_unknown_path_redirects_to_root(page: Page, base_url: str) -> None:
    page.goto(f"{base_url.rstrip('/')}/unknown-path")
    expect(page).to_have_url(re.compile(rf"{re.escape(base_url.rstrip('/'))}/?$"))
    expect(page.get_by_text("Map Workspace")).to_be_visible()


###############################################################################
def test_missing_conversation_snapshot_resets_stale_state(
    page: Page, base_url: str
) -> None:
    _stub_settings_api(page, include_conversation_snapshot=False)
    _seed_persisted_state(page, _base_state())
    page.goto(base_url)
    expect(page.get_by_label("Chat message")).to_have_value("draft should persist")
    expect(page.get_by_text("show map at 41.9028, 12.4964")).not_to_be_visible()
    expect(page.locator(".maplibregl-canvas")).to_have_count(0)
    expect(page.get_by_text("Map Workspace")).to_be_visible()


###############################################################################
def test_corrupted_session_storage_resets_to_defaults(
    page: Page, base_url: str
) -> None:
    storage_key_literal = json.dumps(STORAGE_KEY)
    page.add_init_script(
        f"""
        (() => {{
          window.sessionStorage.setItem({storage_key_literal}, "{{not-json");
        }})();
        """
    )
    page.goto(base_url)
    expect(page.get_by_label("Chat message")).to_have_value("")
    expect(page.get_by_text("Map Workspace")).to_be_visible()


###############################################################################
def test_expired_state_resets_to_defaults(page: Page, base_url: str) -> None:
    old_timestamp = int((time.time() - (7 * 60 * 60)) * 1000)
    _seed_persisted_state(page, _base_state(saved_at=old_timestamp))
    page.goto(base_url)
    expect(page.get_by_label("Chat message")).to_have_value("")
    expect(page.get_by_text("Map Workspace")).to_be_visible()


###############################################################################
def test_stale_overlay_ids_are_ignored_and_notice_shown(
    page: Page, base_url: str
) -> None:
    _stub_settings_api(page)
    stale_state = _base_state()
    stale_state["chatPage"]["mapState"]["overlayVisibility"]["removed_overlay"] = True
    stale_state["chatPage"]["mapState"]["overlayOpacity"]["removed_overlay"] = 0.75
    _seed_persisted_state(page, stale_state)
    page.goto(base_url)
    expect(page.locator(".maplibregl-canvas")).to_be_visible()
