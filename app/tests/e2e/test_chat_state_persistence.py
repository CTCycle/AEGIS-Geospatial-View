from __future__ import annotations

import json
import re
import time
from typing import Any

from playwright.sync_api import Page, Route, expect

from tests.e2e.helpers.chat_stub_payloads import model_settings_payload


STORAGE_KEY = "aegis:webapp-state:v3"
TAB_KEY = "aegis:webapp-tab-id:v1"
HEARTBEAT_PREFIX = "aegis:webapp-tab-heartbeat:v1:"


def _json_ok(route: Route, payload: dict[str, Any]) -> None:
    route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))


def _stub_settings_api(page: Page) -> None:
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


def _seed_persisted_state(page: Page, state: dict[str, Any], tab_id: str) -> None:
    payload = dict(state)
    payload["tabId"] = tab_id
    payload_literal = json.dumps(payload)
    storage_key_literal = json.dumps(STORAGE_KEY)
    tab_key_literal = json.dumps(TAB_KEY)
    page.add_init_script(
        f"""
        (() => {{
          const payload = {payload_literal};
          window.sessionStorage.setItem({tab_key_literal}, payload.tabId);
          window.sessionStorage.setItem({storage_key_literal}, JSON.stringify(payload));
        }})();
        """
    )


def _base_state(saved_at: int | None = None) -> dict[str, Any]:
    return {
        "version": 3,
        "savedAt": saved_at or int(time.time() * 1000),
        "chatPage": {
            "toolbarWidth": 520,
            "isToolbarCollapsed": False,
            "payload": {
                "map_session": {
                    "center": {"latitude": 41.9028, "longitude": 12.4964},
                    "bounds": [12.3, 41.8, 12.7, 42.0],
                    "basemap": {
                        "id": "osm_default",
                        "label": "OpenStreetMap",
                        "provider": "osm",
                        "type": "tile",
                        "tile_url": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
                        "requires_key": False,
                    },
                    "overlays": [
                        {
                            "id": "openaq_air_quality",
                            "label": "OpenAQ Air Quality",
                            "provider": "openaq",
                            "type": "tile",
                            "url": "https://example.test/openaq/{z}/{x}/{y}.png",
                            "default_opacity": 0.55,
                            "requires_key": False,
                        }
                    ],
                    "compliance_warnings": [],
                }
            },
            "chatPanel": {
                "sessionId": 11,
                "conversationNonce": 5,
                "messages": [
                    {"role": "user", "content": "show map at 41.9028, 12.4964"},
                    {"role": "assistant", "content": "Search executed successfully."},
                ],
                "mapSession": {
                    "session_id": "persisted-map-session",
                    "resolved_location": {
                        "label": "Rome, Italy",
                        "latitude": 41.9028,
                        "longitude": 12.4964,
                    },
                    "basemap_id": "osm_default",
                    "overlay_ids": ["openaq_air_quality"],
                    "viewport": {
                        "center_latitude": 41.9028,
                        "center_longitude": 12.4964,
                        "radius_m": 2500.0,
                        "bbox": [12.3, 41.8, 12.7, 42.0],
                    },
                    "payload": {},
                    "center": {"latitude": 41.9028, "longitude": 12.4964},
                    "bounds": [12.3, 41.8, 12.7, 42.0],
                    "basemap": {
                        "id": "osm_default",
                        "label": "OpenStreetMap",
                        "provider": "osm",
                        "type": "tile",
                        "tile_url": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
                        "requires_key": False,
                    },
                    "overlays": [
                        {
                            "id": "openaq_air_quality",
                            "label": "OpenAQ Air Quality",
                            "provider": "openaq",
                            "type": "tile",
                            "url": "https://example.test/openaq/{z}/{x}/{y}.png",
                            "default_opacity": 0.55,
                            "requires_key": False,
                        }
                    ],
                    "compliance_warnings": [],
                },
                "status": "Complete",
                "assistantDraft": "",
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
            "providerMode": "cloud",
            "statusText": "Ready",
            "scrollY": 10,
            "modelGridScrollTop": 120,
        },
    }


def test_refresh_same_tab_restores_chat_and_map_state(
    page: Page, base_url: str
) -> None:
    _stub_settings_api(page)
    _seed_persisted_state(page, _base_state(), "persist-tab-1")
    page.goto(base_url)
    expect(page.get_by_label("Chat message")).to_have_value("draft should persist")
    expect(page.get_by_text("show map at 41.9028, 12.4964")).to_be_visible()
    expect(page.locator(".maplibregl-canvas")).to_be_visible()


def test_back_forward_between_routes_restores_both_states(
    page: Page, base_url: str
) -> None:
    _stub_settings_api(page)
    _seed_persisted_state(page, _base_state(), "persist-tab-2")
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


def test_unknown_path_redirects_to_root(page: Page, base_url: str) -> None:
    page.goto(f"{base_url.rstrip('/')}/unknown-path")
    expect(page).to_have_url(re.compile(rf"{re.escape(base_url.rstrip('/'))}/?$"))
    expect(page.get_by_text("Enter a location-based request to begin.")).to_be_visible()


def test_duplicate_tab_isolation_rotates_owner_and_resets_state(
    page: Page, base_url: str
) -> None:
    _stub_settings_api(page)
    state = _base_state()
    _seed_persisted_state(page, state, "dup-tab")
    tab_literal = json.dumps("dup-tab")
    prefix_literal = json.dumps(HEARTBEAT_PREFIX)
    page.add_init_script(
        f"""
        (() => {{
          const tabId = {tab_literal};
          const heartbeatPrefix = {prefix_literal};
          window.localStorage.setItem(heartbeatPrefix + tabId, String(Date.now()));
        }})();
        """
    )
    page.goto(base_url)
    expect(page.get_by_label("Chat message")).to_have_value("")
    expect(page.get_by_text("Enter a location-based request to begin.")).to_be_visible()


def test_corrupted_session_storage_resets_to_defaults(
    page: Page, base_url: str
) -> None:
    storage_key_literal = json.dumps(STORAGE_KEY)
    tab_key_literal = json.dumps(TAB_KEY)
    page.add_init_script(
        f"""
        (() => {{
          window.sessionStorage.setItem({tab_key_literal}, "bad-tab");
          window.sessionStorage.setItem({storage_key_literal}, "{{not-json");
        }})();
        """
    )
    page.goto(base_url)
    expect(page.get_by_label("Chat message")).to_have_value("")
    expect(page.get_by_text("Enter a location-based request to begin.")).to_be_visible()


def test_expired_state_resets_to_defaults(page: Page, base_url: str) -> None:
    old_timestamp = int((time.time() - (7 * 60 * 60)) * 1000)
    _seed_persisted_state(page, _base_state(saved_at=old_timestamp), "expired-tab")
    page.goto(base_url)
    expect(page.get_by_label("Chat message")).to_have_value("")
    expect(page.get_by_text("Enter a location-based request to begin.")).to_be_visible()


def test_stale_overlay_ids_are_ignored_and_notice_shown(
    page: Page, base_url: str
) -> None:
    stale_state = _base_state()
    stale_state["chatPage"]["mapState"]["overlayVisibility"]["removed_overlay"] = True
    stale_state["chatPage"]["mapState"]["overlayOpacity"]["removed_overlay"] = 0.75
    _seed_persisted_state(page, stale_state, "overlay-tab")
    page.goto(base_url)
    expect(page.locator(".maplibregl-canvas")).to_be_visible()
