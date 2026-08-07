from __future__ import annotations

import base64
import json
import re
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from playwright.sync_api import Page, Route, expect

from tests.e2e.helpers.chat_stub_payloads import (
    chat_turn_map_response,
    chat_turn_text_only_response,
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
def _sse_event(
    *,
    conversation_id: str,
    run_id: str,
    sequence: int,
    event_type: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "event_id": f"evt-{sequence}",
        "sequence": sequence,
        "conversation_id": conversation_id,
        "run_id": run_id,
        "run_version": 1,
        "type": event_type,
        "timestamp": datetime.now(UTC).isoformat(),
        "visibility": "user",
        "payload": payload,
    }

###############################################################################
def _sse_frame(event: dict[str, Any]) -> str:
    return (
        f"id: {event['event_id']}\n"
        f"event: {event['type']}\n"
        f"data: {json.dumps(event)}\n\n"
    )

###############################################################################
def _run_event_stream(
    *,
    conversation_id: str,
    run_id: str,
    turn_payload: dict[str, Any],
) -> str:
    assistant_message = str(turn_payload.get("assistant_message", ""))
    completed_payload = {
        "operation": turn_payload.get("operation"),
        "map_session": turn_payload.get("map_session"),
        "memory_snapshot": turn_payload.get("memory_snapshot", {}),
        "context_usage": turn_payload.get("context_usage"),
    }
    events = [
        _sse_event(
            conversation_id=conversation_id,
            run_id=run_id,
            sequence=1,
            event_type="progress",
            payload={
                "stage": "understanding_request",
                "label": "Understanding the request",
            },
        ),
        _sse_event(
            conversation_id=conversation_id,
            run_id=run_id,
            sequence=2,
            event_type="assistant_text_completed",
            payload={"content": assistant_message},
        ),
        _sse_event(
            conversation_id=conversation_id,
            run_id=run_id,
            sequence=3,
            event_type="completed",
            payload=completed_payload,
        ),
    ]
    return "".join(_sse_frame(event) for event in events)

###############################################################################
def _setup_stub_harness(
    page: Page,
    *,
    settings_payload: dict[str, Any] | None = None,
    models_payload: dict[str, Any] | None = None,
    turn_payload_factory: Callable[[str], dict[str, Any]] | None = None,
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

    active_settings = dict(settings_payload or selected_agent_settings_payload())
    active_models = models_payload or model_catalog_payload()
    captured_put_payloads = put_payloads if put_payloads is not None else []
    run_turn_payloads: dict[str, dict[str, Any]] = {}

    def handle_settings(route: Route) -> None:
        method = route.request.method.upper()
        if method == "GET":
            _json_ok(route, active_settings)
            return
        if method == "PUT":
            payload = _request_json(route)
            if payload:
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
        message = str(_request_json(route).get("message", ""))
        _json_ok(route, turn_payload_factory(message))

    def handle_create_conversation(route: Route) -> None:
        _json_ok(route, {"conversation_id": "conversation-e2e", "title": "E2E"})

    def handle_create_run(route: Route) -> None:
        request_body = _request_json(route)
        message = str(request_body.get("message", ""))
        run_id = f"run-{len(run_turn_payloads) + 1}"
        if turn_payload_factory is None:
            turn_payload = chat_turn_map_response(9001, "Search executed successfully.")
        else:
            turn_payload = turn_payload_factory(message)
        run_turn_payloads[run_id] = turn_payload
        route.fulfill(
            status=202,
            content_type="application/json",
            body=json.dumps(
                {
                    "conversation_id": "conversation-e2e",
                    "run_id": run_id,
                    "run_version": 1,
                    "state": "running",
                    "stream_url": f"/api/conversations/conversation-e2e/runs/{run_id}/events",
                    "message": message,
                }
            ),
        )

    def handle_run_events(route: Route) -> None:
        match = re.search(r"/runs/([^/]+)/events", route.request.url)
        run_id = match.group(1) if match else "run-1"
        turn_payload = run_turn_payloads.get(
            run_id, chat_turn_map_response(9001, "Search executed successfully.")
        )
        route.fulfill(
            status=200,
            content_type="text/event-stream",
            body=_run_event_stream(
                conversation_id="conversation-e2e",
                run_id=run_id,
                turn_payload=turn_payload,
            ),
        )

    page.route(re.compile(r".*/api/chat/settings.*"), handle_settings)
    page.route(
        re.compile(r".*/api/chat/models.*"),
        lambda route: _json_ok(route, active_models),
    )
    page.route(
        re.compile(r".*/api/geospatial/capabilities.*"),
        lambda route: _json_ok(
            route,
            {
                "providers": [
                    {
                        "id": "openstreetmap",
                        "name": "OpenStreetMap",
                        "kind": "provider",
                        "provider": "openstreetmap",
                        "description": "Public map data provider.",
                        "requires_credentials": False,
                        "is_available": True,
                    }
                ],
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
                "overlays": [
                    {
                        "id": "openaq_air_quality",
                        "name": "OpenAQ Air Quality",
                        "kind": "overlay",
                        "provider": "openaq",
                        "description": "Air quality overlay fixture.",
                        "requires_credentials": False,
                        "is_available": True,
                    }
                ],
                "cameras": [],
                "transit": [],
                "tools": [
                    {
                        "id": "location_to_coordinates",
                        "name": "Location to coordinates",
                        "kind": "tool",
                        "provider": "aegis",
                        "description": "Direct coordinate lookup.",
                        "requires_credentials": False,
                        "is_available": True,
                    }
                ],
            },
        ),
    )
    page.route(re.compile(r".*/api/chat/turn.*"), handle_turn)
    page.route(re.compile(r".*/api/conversations$"), handle_create_conversation)
    page.route(
        re.compile(r".*/api/conversations/[^/]+/runs$"), handle_create_run
    )
    page.route(
        re.compile(r".*/api/conversations/[^/]+/runs/[^/]+/events.*"),
        handle_run_events,
    )
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
            else chat_turn_map_response(9001, "Search executed successfully.")
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
    expect(page.get_by_role("complementary", name="Selected agent model")).to_be_visible(
        timeout=15000
    )

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
    assert (
        layout_metrics["rightRect"]["top"] >= layout_metrics["leftRect"]["bottom"] - 1
    )

###############################################################################
def test_model_card_selects_the_single_agent_model(page: Page, base_url: str) -> None:
    put_payloads: list[dict[str, Any]] = []
    expected_initial = selected_agent_settings_payload()
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

    assert put_payloads, "Expected PUT /api/chat/settings payload to be captured."
    payload = put_payloads[-1]
    if "agent_model_provider" not in payload:
        matching_payloads = [
            item for item in put_payloads if "agent_model_provider" in item
        ]
        assert matching_payloads, f"No model settings payload captured: {put_payloads}"
        payload = matching_payloads[-1]

    assert payload["agent_model_provider"] == "openai"
    assert payload["agent_model_name"] == "gpt-5-mini"
    assert "ollama_url" not in payload
    assert "openai_base_url" not in payload
    assert "google_base_url" not in payload
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
        turn_payload_factory=lambda _message: chat_turn_text_only_response(
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
    def turn_payload(message: str) -> dict[str, Any]:
        message = message.lower()
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

    page.get_by_role("button", name="Start new chat").click()
    expect(page.get_by_label("Chat message")).to_be_visible(timeout=15000)
    composer.fill("place search for Rome city center")
    page.get_by_role("button", name="Send").click()
    expect(
        page.get_by_text("Place search rendered with an interactive map.")
    ).to_be_visible(timeout=15000)
    expect(page.locator(".maplibregl-canvas")).to_be_visible(timeout=15000)
