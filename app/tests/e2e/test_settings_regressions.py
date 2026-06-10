from __future__ import annotations

import base64
import json
import re
from collections.abc import Callable
from typing import Any

from playwright.sync_api import Page, Route, expect

from tests.e2e.helpers.chat_stub_payloads import (
    chat_turn_map_response,
    chat_turn_text_only_response,
    model_catalog_payload,
    split_role_settings_payload,
)

PNG_1X1_TRANSPARENT = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Jte8AAAAASUVORK5CYII="
)


###############################################################################
def _json_ok(route: Route, payload: dict[str, Any]) -> None:
    route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))


###############################################################################
def _setup_stub_harness(
    page: Page,
    *,
    settings_payload: dict[str, Any] | None = None,
    models_payload: dict[str, Any] | None = None,
    turn_payload_factory: Callable[[Route], dict[str, Any]] | None = None,
    put_payloads: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    page.add_init_script(
        """
        () => {
          window.sessionStorage.clear();
          window.localStorage.clear();
        }
        """
    )

    active_settings = dict(settings_payload or split_role_settings_payload())
    active_models = models_payload or model_catalog_payload()
    captured_put_payloads = put_payloads if put_payloads is not None else []

    def handle_settings(route: Route) -> None:
        method = route.request.method.upper()
        if method == "GET":
            _json_ok(route, active_settings)
            return
        if method == "PUT":
            payload = route.request.post_data_json or {}
            if isinstance(payload, dict):
                captured_put_payloads.append(payload)
                active_settings.update(payload)
            _json_ok(route, active_settings)
            return
        route.fulfill(
            status=405,
            content_type="application/json",
            body=json.dumps({"detail": "Method not allowed"}),
        )

    def handle_turn(route: Route) -> None:
        if turn_payload_factory is None:
            _json_ok(
                route, chat_turn_map_response(9001, "Search executed successfully.")
            )
            return
        _json_ok(route, turn_payload_factory(route))

    page.route(re.compile(r".*/api/chat/settings.*"), handle_settings)
    page.route(
        re.compile(r".*/api/chat/models.*"),
        lambda route: _json_ok(route, active_models),
    )
    page.route(
        re.compile(r".*/api/maps/catalog.*"),
        lambda route: _json_ok(
            route,
            {
                "providers": [],
                "basemaps": [
                    {
                        "id": "osm_default",
                        "name": "OpenStreetMap",
                        "kind": "basemap",
                        "provider": "openstreetmap",
                        "coverage": "global",
                        "description": "Standard street map tiles.",
                        "requires_credentials": False,
                        "is_available": True,
                    }
                ],
                "overlays": [],
            },
        ),
    )
    page.route(re.compile(r".*/api/chat/turn.*"), handle_turn)
    page.route(
        re.compile(r".*/api/maps/basemaps/osm/\d+/\d+/\d+\.png$"),
        lambda route: route.fulfill(
            status=200, content_type="image/png", body=PNG_1X1_TRANSPARENT
        ),
    )
    return captured_put_payloads


###############################################################################
def test_settings_mobile_layout_has_no_overlap_at_320px(
    page: Page, base_url: str
) -> None:
    _setup_stub_harness(page)
    page.set_viewport_size({"width": 320, "height": 700})

    page.goto(f"{base_url.rstrip('/')}/settings?mode=cloud")

    expect(page.locator(".model-card").first).to_be_visible(timeout=15000)
    expect(page.locator(".settings-page__stats-mobile-card").first).to_be_visible(
        timeout=15000
    )

    layout_metrics = page.evaluate(
        """
        () => {
          const left = document.querySelector('.settings-page__left-column');
          const right = document.querySelector('.settings-page__right-column');
          const cards = Array.from(document.querySelectorAll('.model-card'));
          const statCards = Array.from(document.querySelectorAll('.settings-page__stats-mobile-card'));
          const asRect = (el) => {
            const r = el.getBoundingClientRect();
            return { left: r.left, right: r.right, top: r.top, bottom: r.bottom, width: r.width, height: r.height };
          };
          const intersects = (a, b) => (
            a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top
          );
          const modelRects = cards.map(asRect).filter((rect) => rect.width > 0 && rect.height > 0);
          const statsRects = statCards.map(asRect).filter((rect) => rect.width > 0 && rect.height > 0);
          const overlaps = [];
          modelRects.forEach((modelRect, modelIndex) => {
            statsRects.forEach((statsRect, statsIndex) => {
              if (intersects(modelRect, statsRect)) {
                overlaps.push({ modelIndex, statsIndex });
              }
            });
          });
          return {
            overlaps,
            leftRect: left ? asRect(left) : null,
            rightRect: right ? asRect(right) : null,
          };
        }
        """
    )

    assert layout_metrics["overlaps"] == []
    assert layout_metrics["leftRect"] is not None
    assert layout_metrics["rightRect"] is not None
    assert (
        layout_metrics["rightRect"]["top"] >= layout_metrics["leftRect"]["bottom"] - 1
    )


###############################################################################
def test_role_assignment_updates_only_requested_role(page: Page, base_url: str) -> None:
    put_payloads: list[dict[str, Any]] = []
    expected_initial = split_role_settings_payload()
    _setup_stub_harness(
        page, settings_payload=expected_initial, put_payloads=put_payloads
    )

    page.goto(f"{base_url.rstrip('/')}/settings")

    model_card = (
        page.locator("article.model-card")
        .filter(has=page.get_by_role("heading", name="gpt-5-mini"))
        .first
    )
    expect(model_card).to_be_visible(timeout=15000)
    model_card.get_by_role("button", name="Parser").click()

    expect(page.get_by_text("Selected gpt-5-mini for parser")).to_be_visible(
        timeout=15000
    )
    assert put_payloads, "Expected PUT /api/chat/settings payload to be captured."
    payload = put_payloads[-1]

    assert payload["parser_model_provider"] == "openai"
    assert payload["parser_model_name"] == "gpt-5-mini"
    assert payload["chat_model_provider"] == expected_initial["chat_model_provider"]
    assert payload["chat_model_name"] == expected_initial["chat_model_name"]
    assert payload["agent_model_provider"] == expected_initial["agent_model_provider"]
    assert payload["agent_model_name"] == expected_initial["agent_model_name"]
    assert payload["ollama_url"] == expected_initial["ollama_url"]
    assert payload["openai_base_url"] == expected_initial["openai_base_url"]
    assert payload["google_base_url"] == expected_initial["google_base_url"]
    assert set(payload["credentials"].keys()) == set(expected_initial["credentials"].keys())
    assert payload["active_provider_mode"] == "cloud"
    assert "credential_health" not in payload
    assert all("api_key" not in values for values in payload["credentials"].values())


###############################################################################
def test_capabilities_tables_do_not_clip_desktop_columns(
    page: Page, base_url: str
) -> None:
    _setup_stub_harness(page)
    page.set_viewport_size({"width": 1366, "height": 768})
    page.goto(f"{base_url.rstrip('/')}/geodata")

    expect(page.get_by_role("heading", name="Map Types")).to_be_visible(timeout=15000)

    metrics = page.evaluate(
        """
        () => {
          const page = document.querySelector('.capabilities-page');
          const tableWraps = Array.from(document.querySelectorAll('.capability-table-wrap'));
          const pageRect = page.getBoundingClientRect();
          return {
            bodyOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
            wrappedTables: tableWraps.map((wrap) => {
              const rect = wrap.getBoundingClientRect();
              return { left: rect.left, right: rect.right, pageRight: pageRect.right };
            }),
          };
        }
        """
    )

    assert metrics["bodyOverflow"] <= 1
    assert metrics["wrappedTables"]
    assert all(item["right"] <= item["pageRight"] + 1 for item in metrics["wrappedTables"])


###############################################################################
def test_chat_composer_does_not_cover_latest_assistant_message(
    page: Page, base_url: str
) -> None:
    _setup_stub_harness(
        page,
        turn_payload_factory=lambda route: chat_turn_text_only_response(
            12001,
            "This is the latest assistant response and it must remain visible above the composer.",
        ),
    )
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(base_url)

    page.get_by_label("Chat message").fill("show status")
    page.get_by_role("button", name="Send").click()
    latest = page.get_by_text(
        "This is the latest assistant response and it must remain visible above the composer."
    )
    expect(latest).to_be_visible(timeout=15000)

    metrics = page.evaluate(
        """
        () => {
          const assistant = Array.from(document.querySelectorAll('.chat-message--assistant')).at(-1);
          const composer = document.querySelector('.chat-composer');
          const a = assistant.getBoundingClientRect();
          const c = composer.getBoundingClientRect();
          return { assistantBottom: a.bottom, composerTop: c.top };
        }
        """
    )

    assert metrics["assistantBottom"] <= metrics["composerTop"] + 1


###############################################################################
def test_settings_query_params_do_not_leak_back_to_chat(
    page: Page, base_url: str
) -> None:
    _setup_stub_harness(page)

    page.goto(f"{base_url.rstrip('/')}/settings?mode=cloud")
    expect(page).to_have_url(re.compile(r".*/settings\?mode=cloud$"))

    page.get_by_role("link", name="Search").click()
    expect(page.get_by_label("Chat message")).to_be_visible(timeout=15000)

    path = page.evaluate("() => window.location.pathname")
    query = page.evaluate("() => window.location.search")
    assert path == "/"
    assert query == ""


###############################################################################
def test_coordinate_lookup_and_place_search_follow_distinct_ui_paths(
    page: Page, base_url: str
) -> None:
    def turn_payload(route: Route) -> dict[str, Any]:
        request_body = route.request.post_data_json or {}
        message = str(request_body.get("message", "")).lower()
        if "coordinate" in message:
            return chat_turn_text_only_response(
                11001, "Coordinates identified without map session."
            )
        return chat_turn_map_response(
            11001, "Place search rendered with an interactive map."
        )

    _setup_stub_harness(page, turn_payload_factory=turn_payload)

    page.goto(base_url)
    composer = page.get_by_label("Chat message")

    composer.fill("coordinate lookup for Eiffel Tower")
    page.get_by_role("button", name="Send").click()
    expect(
        page.get_by_text("Coordinates identified without map session.")
    ).to_be_visible(timeout=15000)
    expect(page.locator(".maplibregl-canvas")).to_have_count(0)
    expect(page.locator(".overlay-controls")).to_have_count(0)

    composer.fill("place search for Rome city center")
    page.get_by_role("button", name="Send").click()
    expect(
        page.get_by_text("Place search rendered with an interactive map.")
    ).to_be_visible(timeout=15000)
    expect(page.locator(".maplibregl-canvas")).to_be_visible(timeout=15000)
