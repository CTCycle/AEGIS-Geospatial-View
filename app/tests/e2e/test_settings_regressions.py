from __future__ import annotations

import base64
import json
import re
from collections.abc import Callable
from typing import Any

from playwright.sync_api import Page, Route, expect

from tests.e2e.helpers.chat_stub_payloads import (
    chat_completion_map_payload,
    chat_completion_text_payload,
    geospatial_catalog_payload,
    model_catalog_payload,
    selected_agent_settings_payload,
)
from tests.e2e.helpers.realtime_stub import register_realtime_stub

PNG_1X1_TRANSPARENT = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGBgAAAABQABpfZFQAAAAABJRU5ErkJggg=="
)


###############################################################################
def _json_ok(route: Route, payload: dict[str, Any]) -> None:
    route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))


###############################################################################
def _request_json(route: Route) -> dict[str, Any]:
    raw_post_data = getattr(route.request, "post_data", None)
    if callable(raw_post_data):
        raw_post_data = raw_post_data()
    if isinstance(raw_post_data, str) and raw_post_data.strip():
        try:
            payload = json.loads(raw_post_data)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            return payload
    try:
        payload = route.request.post_data_json()
    except Exception:  # noqa: BLE001
        return {}
    return payload if isinstance(payload, dict) else {}


###############################################################################
def _setup_stub_harness(
    page: Page,
    *,
    settings_payload: dict[str, Any] | None = None,
    models_payload: dict[str, Any] | None = None,
    turn_payload_factory: Callable[[str], dict[str, Any]] | None = None,
    patch_payloads: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    page.add_init_script(
        """
        () => {
          window.sessionStorage.clear();
          window.localStorage.clear();
        }
        """
    )

    active_settings = dict(settings_payload or selected_agent_settings_payload())
    active_models = models_payload or model_catalog_payload()
    captured_patch_payloads = patch_payloads if patch_payloads is not None else []

    def handle_settings(route: Route) -> None:
        method = route.request.method.upper()
        if method == "GET":
            _json_ok(route, active_settings)
            return
        if method == "PATCH":
            payload = _request_json(route)
            if payload:
                captured_patch_payloads.append(payload)
            active_settings.update(payload)
            _json_ok(route, active_settings)
            return
        route.fulfill(
            status=405,
            content_type="application/json",
            body=json.dumps({"detail": "Method not allowed"}),
        )

    def handle_create_conversation(route: Route) -> None:
        _json_ok(route, {"conversation_id": "conversation-e2e", "title": "E2E"})

    page.route(re.compile(r".*/api/chat/settings.*"), handle_settings)
    page.route(
        re.compile(r".*/api/chat/models.*"),
        lambda route: _json_ok(route, active_models),
    )
    page.route(
        re.compile(r".*/api/geospatial/capabilities.*"),
        lambda route: _json_ok(route, geospatial_catalog_payload()),
    )
    page.route(re.compile(r".*/api/conversations$"), handle_create_conversation)
    page.route(
        re.compile(r".*/api/geospatial/tiles/osm_default/\d+/\d+/\d+\.png(?:\?.*)?$"),
        lambda route: route.fulfill(
            status=200, content_type="image/png", body=PNG_1X1_TRANSPARENT
        ),
    )
    register_realtime_stub(
        page,
        lambda message, _run_number: (
            turn_payload_factory(message)
            if turn_payload_factory is not None
            else chat_completion_map_payload(9001, "Search executed successfully.")
        ),
    )
    return captured_patch_payloads


###############################################################################
def test_settings_layout_has_no_overlap_at_minimum_desktop_width(
    page: Page, base_url: str
) -> None:
    _setup_stub_harness(page)
    page.set_viewport_size({"width": 1024, "height": 700})

    page.goto(f"{base_url.rstrip('/')}/settings?mode=cloud")

    expect(page.locator(".model-card").first).to_be_visible(timeout=15000)
    expect(
        page.get_by_role("complementary", name="Selected agent model")
    ).to_be_visible(timeout=15000)

    layout_metrics = page.evaluate(
        """
        () => {
          const left = document.querySelector('.settings-page__left-column');
          const right = document.querySelector('.settings-page__right-column');
          const asRect = (el) => {
            const r = el.getBoundingClientRect();
            return { left: r.left, right: r.right, top: r.top, bottom: r.bottom, width: r.width, height: r.height };
          };
          return {
            leftRect: left ? asRect(left) : null,
            rightRect: right ? asRect(right) : null,
            bodyOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
          };
        }
        """
    )

    assert layout_metrics["leftRect"] is not None
    assert layout_metrics["rightRect"] is not None
    assert layout_metrics["bodyOverflow"] <= 1
    left = layout_metrics["leftRect"]
    right = layout_metrics["rightRect"]
    assert (
        left["right"] <= right["left"] + 1
        or right["right"] <= left["left"] + 1
        or left["bottom"] <= right["top"] + 1
        or right["bottom"] <= left["top"] + 1
    )


###############################################################################
def test_model_card_selects_the_single_agent_model(page: Page, base_url: str) -> None:
    patch_payloads: list[dict[str, Any]] = []
    expected_initial = selected_agent_settings_payload()
    _setup_stub_harness(
        page, settings_payload=expected_initial, patch_payloads=patch_payloads
    )

    page.goto(f"{base_url.rstrip('/')}/settings")

    model_card = (
        page.locator("article.model-card")
        .filter(has=page.get_by_role("heading", name="gpt-5-mini"))
        .first
    )
    expect(model_card).to_be_visible(timeout=15000)
    selection_button = model_card.get_by_role(
        "button", name="Select as agent model: gpt-5-mini"
    )
    selection_button.focus()
    page.keyboard.press("Enter")

    selected_button = model_card.get_by_role(
        "button", name="Selected agent model: gpt-5-mini"
    )
    expect(selected_button).to_have_attribute("aria-pressed", "true")
    selected_button.focus()
    page.keyboard.press("Space")
    summary = page.get_by_role("complementary", name="Selected agent model")
    expect(summary.get_by_role("heading", name="gpt-5-mini")).to_be_visible()

    assert patch_payloads, "Expected PATCH /api/chat/settings payload to be captured."
    payload = patch_payloads[-1]
    if "agent_model_provider" not in payload:
        matching_payloads = [
            item for item in patch_payloads if "agent_model_provider" in item
        ]
        assert matching_payloads, f"No model settings payload captured: {patch_payloads}"
        payload = matching_payloads[-1]

    assert payload["agent_model_provider"] == "openai"
    assert payload["agent_model_name"] == "gpt-5-mini"
    assert "ollama_url" not in payload
    assert "openai_base_url" not in payload
    assert "google_base_url" not in payload
    assert set(payload["credentials"].keys()) == set(
        expected_initial["credentials"].keys()
    )
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
    assert all(
        item["right"] <= item["pageRight"] + 1 for item in metrics["wrappedTables"]
    )


###############################################################################
def test_chat_composer_does_not_cover_latest_assistant_message(
    page: Page, base_url: str
) -> None:
    _setup_stub_harness(
        page,
        turn_payload_factory=lambda _message: chat_completion_text_payload(
            12001,
            "This is the latest assistant response and it must remain visible above the composer.",
        ),
    )
    page.set_viewport_size({"width": 1024, "height": 844})
    page.goto(base_url)

    page.get_by_label("Chat message").fill("show status")
    page.get_by_role("button", name="Send message").click()
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
    expect(page).to_have_url(re.compile(r".*/settings$"))

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
    def turn_payload(message: str) -> dict[str, Any]:
        message = message.lower()
        if "coordinate" in message:
            return chat_completion_text_payload(
                11001, "Coordinates identified without map session."
            )
        return chat_completion_map_payload(
            11001, "Place search rendered with an interactive map."
        )

    _setup_stub_harness(page, turn_payload_factory=turn_payload)

    page.goto(base_url)
    composer = page.get_by_label("Chat message")

    composer.fill("coordinate lookup for Eiffel Tower")
    page.get_by_role("button", name="Send message").click()
    expect(
        page.get_by_text("Coordinates identified without map session.")
    ).to_be_visible(timeout=15000)
    expect(page.locator(".maplibregl-canvas")).to_have_count(0)
    expect(page.locator(".overlay-controls")).to_have_count(0)

    page.get_by_role("button", name="Start new chat").click()
    expect(page.get_by_label("Chat message")).to_be_visible(timeout=15000)
    composer.fill("place search for Rome city center")
    page.get_by_role("button", name="Send message").click()
    expect(
        page.get_by_text("Place search rendered with an interactive map.")
    ).to_be_visible(timeout=15000)
    expect(page.locator(".maplibregl-canvas")).to_be_visible(timeout=15000)
