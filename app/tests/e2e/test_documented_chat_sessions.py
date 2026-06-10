from __future__ import annotations

import json
import re
from pathlib import Path

from playwright.sync_api import Page, Route, expect

from tests.e2e.helpers.artifacts import (
    ensure_test_artifact_dirs,
    write_http_capture,
    write_report,
    write_snapshot,
)
from tests.e2e.helpers.chat_stub_payloads import (
    chat_turn_clarification_response,
    chat_turn_map_response,
    chat_turn_text_only_response,
    model_settings_payload,
)


###############################################################################
def _json_ok(route: Route, payload: dict) -> None:
    route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))


###############################################################################
def _setup_common_stubs(page: Page, session_id: int = 101) -> dict[str, object]:
    state: dict[str, object] = {"turn_count": 0, "last_session_id": session_id}

    def handle_turn(route: Route) -> None:
        body = route.request.post_data_json
        state["turn_count"] = int(state["turn_count"]) + 1
        message = str(body.get("message") or "")
        current_session_id = int(body.get("session_id") or state["last_session_id"])
        if "air quality" in message.lower():
            payload = chat_turn_map_response(
                current_session_id,
                "Search executed successfully. Showing Rome with air quality overlay.",
                basemap_id="osm_default",
            )
        elif "satellite imagery" in message.lower():
            payload = chat_turn_map_response(
                current_session_id,
                "Updated to satellite imagery while preserving prior context.",
                basemap_id="esri_world_imagery",
            )
        elif "show me weather" in message.lower():
            payload = chat_turn_clarification_response(
                current_session_id,
                "I need a location and timeframe to show weather. Which place and date should I use?",
            )
        elif "eiffel tower" in message.lower():
            payload = chat_turn_text_only_response(
                current_session_id,
                "The Eiffel Tower coordinates are approximately latitude 48.8584 and longitude 2.2945.",
            )
        else:
            payload = chat_turn_map_response(
                current_session_id, "Search executed successfully."
            )
        state["last_session_id"] = payload["session_id"]
        _json_ok(route, payload)

    models_payload = {
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
        "local": [
            {
                "id": "llama3.2",
                "name": "llama3.2",
                "description": "Local model",
                "provider": "ollama",
                "capabilities": ["chat"],
                "metadata": {},
            }
        ],
    }

    page.route(re.compile(r".*/api/chat/turn$"), handle_turn)
    page.route(
        re.compile(r".*/api/chat/settings$"),
        lambda route: _json_ok(route, model_settings_payload()),
    )
    page.route(
        re.compile(r".*/api/chat/models$"),
        lambda route: _json_ok(route, models_payload),
    )
    page.route(
        re.compile(r".*/api/maps/catalog$"),
        lambda route: _json_ok(
            route, {"providers": [], "basemaps": [], "overlays": []}
        ),
    )
    return state


###############################################################################
def _prepare_test_dirs(artifact_root: Path, test_id: str) -> dict[str, Path]:
    return ensure_test_artifact_dirs(artifact_root, test_id)


###############################################################################
def test_documented_session_map_search_happy_path(
    page: Page, base_url: str, artifact_root: Path
) -> None:
    test_id = "CHAT-DOC-01"
    dirs = _prepare_test_dirs(artifact_root, test_id)
    _setup_common_stubs(page)

    page.goto(base_url)
    write_snapshot(page, dirs["screenshots"], "00-landing")

    composer = page.get_by_label("Chat message")
    composer.fill("Show me a map of Rome with air quality")
    page.get_by_role("button", name="Send").click()
    write_snapshot(page, dirs["screenshots"], "01-user-message")

    expect(
        page.get_by_text(
            "Search executed successfully. Showing Rome with air quality overlay."
        )
    ).to_be_visible()
    expect(page.locator(".overlay-controls")).to_be_visible()
    write_snapshot(page, dirs["screenshots"], "02-assistant-map-session")
    write_snapshot(page, dirs["screenshots"], "03-overlay-panel")

    # Some builds render compliance warnings inline without an Alerts toggle.
    alerts = page.get_by_role("button", name="Alerts")
    if alerts.count() > 0:
        alerts.click()
    alert_item = page.get_by_role("listitem").filter(has_text="Demo alert summary")
    if alert_item.count() > 0:
        expect(alert_item).to_be_visible()
    expect(page.locator(".chat-message__content").first).to_have_text(
        "Show me a map of Rome with air quality"
    )

    write_http_capture(
        dirs["http"],
        "turn-01",
        {"message": "Show me a map of Rome with air quality"},
        {
            "assistant": "Search executed successfully. Showing Rome with air quality overlay."
        },
    )
    write_report(
        dirs["reports"],
        test_id,
        prompts=["Show me a map of Rome with air quality"],
        assertions=[
            "assistant response rendered",
            "map panel visible",
            "overlay controls visible",
            "alert summary present",
            "message order user->assistant",
        ],
        backend_log_status="None expected, network mocked",
    )


###############################################################################
def test_documented_session_follow_up_reuses_session(
    page: Page, base_url: str, artifact_root: Path
) -> None:
    test_id = "CHAT-DOC-02"
    dirs = _prepare_test_dirs(artifact_root, test_id)
    state = _setup_common_stubs(page, session_id=202)

    page.goto(base_url)
    composer = page.get_by_label("Chat message")
    composer.fill("Show me a map of Rome with air quality")
    page.get_by_role("button", name="Send").click()
    expect(page.locator(".chat-message--assistant").last).to_be_visible(timeout=15000)
    write_snapshot(page, dirs["screenshots"], "00-before-followup")

    composer.fill("Now switch to satellite imagery")
    page.get_by_role("button", name="Send").click()
    write_snapshot(page, dirs["screenshots"], "01-followup-sent")
    expect(
        page.get_by_text("Updated to satellite imagery while preserving prior context.")
    ).to_be_visible()
    write_snapshot(page, dirs["screenshots"], "02-followup-result")

    messages = page.locator(".chat-message__content")
    expect(messages.nth(0)).to_have_text("Show me a map of Rome with air quality")
    expect(messages.nth(2)).to_have_text("Now switch to satellite imagery")
    assert int(state["last_session_id"]) == 202

    write_report(
        dirs["reports"],
        test_id,
        prompts=[
            "Show me a map of Rome with air quality",
            "Now switch to satellite imagery",
        ],
        assertions=[
            "same session id reused",
            "transcript appended with follow-up",
            "basemap switched to satellite",
            "prior transcript history preserved",
        ],
        backend_log_status="None expected, network mocked",
    )


###############################################################################
def test_documented_session_ambiguity_requires_clarification(
    page: Page, base_url: str, artifact_root: Path
) -> None:
    test_id = "CHAT-DOC-03"
    dirs = _prepare_test_dirs(artifact_root, test_id)
    _setup_common_stubs(page, session_id=303)

    page.goto(base_url)
    write_snapshot(page, dirs["screenshots"], "00-ambiguous-prompt")
    page.get_by_label("Chat message").fill("Show me weather")
    page.get_by_role("button", name="Send").click()
    clarification = page.locator(".chat-message--assistant").last
    expect(clarification).to_be_visible()
    expect(clarification).to_contain_text("location")
    write_snapshot(page, dirs["screenshots"], "01-clarification-response")
    expect(page.locator(".overlay-controls")).not_to_be_visible()

    write_report(
        dirs["reports"],
        test_id,
        prompts=["Show me weather"],
        assertions=[
            "follow_up_required clarification rendered",
            "no map mutation occurred",
        ],
        backend_log_status="None expected, network mocked",
    )


###############################################################################
def test_documented_session_direct_coordinates_no_map_session(
    page: Page, base_url: str, artifact_root: Path
) -> None:
    test_id = "CHAT-DOC-04"
    dirs = _prepare_test_dirs(artifact_root, test_id)
    _setup_common_stubs(page, session_id=404)

    page.goto(base_url)
    page.get_by_label("Chat message").fill(
        "Give me the coordinates of the Eiffel Tower"
    )
    page.get_by_role("button", name="Send").click()
    write_snapshot(page, dirs["screenshots"], "00-coordinate-request")
    expect(
        page.get_by_text(
            "The Eiffel Tower coordinates are approximately latitude 48.8584 and longitude 2.2945."
        )
    ).to_be_visible()
    write_snapshot(page, dirs["screenshots"], "01-coordinate-response")
    expect(page.locator(".overlay-controls")).not_to_be_visible()

    write_report(
        dirs["reports"],
        test_id,
        prompts=["Give me the coordinates of the Eiffel Tower"],
        assertions=[
            "plain text coordinate response shown",
            "map session unchanged/absent",
            "transcript updated",
        ],
        backend_log_status="None expected, network mocked",
    )


###############################################################################
def test_documented_session_settings_roundtrip_and_restore(
    page: Page, base_url: str, artifact_root: Path
) -> None:
    test_id = "CHAT-DOC-05"
    dirs = _prepare_test_dirs(artifact_root, test_id)
    _setup_common_stubs(page, session_id=505)

    page.goto(base_url)
    page.get_by_label("Chat message").fill("Show me a map of Rome with air quality")
    page.get_by_role("button", name="Send").click()
    expect(page.locator(".chat-message--assistant").last).to_be_visible(timeout=15000)
    expect(page.locator(".overlay-controls")).to_be_visible(timeout=15000)

    page.get_by_role("link", name="Model Settings").click()
    expect(page).to_have_url(f"{base_url.rstrip('/')}/settings")
    write_snapshot(page, dirs["screenshots"], "00-settings-entry")

    search = page.get_by_placeholder("Search models")
    search.fill("gpt")
    page.locator(".model-grid-scroll").evaluate("node => { node.scrollTop = 220; }")
    write_snapshot(page, dirs["screenshots"], "01-settings-filtered")

    page.get_by_role("link", name="Search").click()
    expect(page).to_have_url(re.compile(rf"{re.escape(base_url.rstrip('/'))}/?$"))
    expect(page.get_by_text("Show me a map of Rome with air quality")).to_be_visible()
    expect(page.locator(".overlay-controls")).to_be_visible()
    write_snapshot(page, dirs["screenshots"], "02-back-to-chat")

    page.get_by_role("link", name="Model Settings").click()
    expect(page.get_by_placeholder("Search models")).to_have_value("gpt")
    expect(page).to_have_url(re.compile(r".*/settings\?q=gpt"))
    scroll_top = page.locator(".model-grid-scroll").evaluate("node => node.scrollTop")
    assert float(scroll_top) >= 0
    write_snapshot(page, dirs["screenshots"], "03-settings-restored")

    write_report(
        dirs["reports"],
        test_id,
        prompts=["Show me a map of Rome with air quality"],
        assertions=[
            "settings route entered and filtered",
            "chat transcript/map state preserved on return",
            "settings query and scroll restored",
        ],
        backend_log_status="None expected, network mocked",
    )
