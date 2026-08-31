from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.helpers.artifacts import (
    ensure_test_artifact_dirs,
    write_http_capture,
    write_log_tail,
    write_report,
    write_snapshot,
)
from tests.e2e.helpers.realtime_stub import register_realtime_stub


###############################################################################
def _check_live_provider(page: Page, api_base_url: str) -> tuple[bool, str]:
    conversation_response = page.request.post(
        f"{api_base_url.rstrip('/')}/api/conversations",
        data={"title": "live provider preflight"},
    )
    if conversation_response.status != 201:
        return False, (
            "Could not create a conversation for live provider preflight "
            f"({conversation_response.status})"
        )
    conversation_id = conversation_response.json().get("conversation_id")
    if not isinstance(conversation_id, str) or not conversation_id:
        return False, "Conversation preflight returned no conversation_id"

    response = page.request.post(
        f"{api_base_url.rstrip('/')}/api/chat/turn",
        data={
            "conversation_id": conversation_id,
            "message": "Give me the coordinates of Rome, Italy",
        },
    )
    if response.status == 200:
        body = response.json()
        assistant = str(body.get("assistant_message") or "").lower()
        if (
            "configured agent model" in assistant
            and "structured extraction" in assistant
        ):
            return False, "Configured agent model cannot perform structured extraction"
        return True, ""
    if response.status in {400, 502, 503}:
        return False, f"Live provider precondition failed with status {response.status}"
    return False, f"Unexpected provider precondition status {response.status}"


###############################################################################
def _assert_clean_backend_tail(tail: str) -> None:
    normalized = tail.lower()
    assert "traceback" not in normalized
    assert "unhandled exception" not in normalized


###############################################################################
def _read_conversation_id(page: Page) -> str | None:
    raw = page.evaluate("() => window.sessionStorage.getItem('aegis:webapp-ui-state:v1')")
    if not raw:
        return None
    data = json.loads(raw)
    chat_page = data.get("chatPage", {})
    chat_panel = chat_page.get("chatPanel", {}) if isinstance(chat_page, dict) else {}
    conversation_id = chat_panel.get("conversationId")
    return (
        conversation_id
        if isinstance(conversation_id, str) and conversation_id
        else None
    )


###############################################################################
def test_live_chat_happy_path(
    page: Page,
    base_url: str,
    api_base_url: str,
    artifact_root: Path,
    read_backend_log_tail,
) -> None:
    test_id = "CHAT-LIVE-01"
    dirs = ensure_test_artifact_dirs(artifact_root, test_id)
    ready, reason = _check_live_provider(page, api_base_url)
    if not ready:
        pytest.skip(reason)

    page.goto(base_url)
    write_snapshot(page, dirs["screenshots"], "00-live-landing")
    page.get_by_label("Chat message").fill("Show me Rome")
    page.get_by_role("button", name="Send message").click()
    write_snapshot(page, dirs["screenshots"], "01-live-request")
    expect(page.locator(".chat-message--assistant").last).to_be_visible(timeout=60000)
    write_snapshot(page, dirs["screenshots"], "02-live-response")

    conversation_id = _read_conversation_id(page)
    assert conversation_id

    tail = read_backend_log_tail(200)
    write_log_tail(dirs["logs"], test_id, tail)
    _assert_clean_backend_tail(tail)
    write_http_capture(
        dirs["http"],
        "turn-01",
        {"message": "Show me Rome"},
        {"conversation_id": conversation_id},
    )
    write_report(
        dirs["reports"],
        test_id,
        prompts=["Show me Rome"],
        assertions=[
            "assistant response rendered",
            "conversation id persisted",
            "backend log tail clean",
        ],
        backend_log_status="clean" if tail.strip() else "empty",
    )


###############################################################################
def test_live_follow_up_same_conversation(
    page: Page,
    base_url: str,
    api_base_url: str,
    artifact_root: Path,
    read_backend_log_tail,
) -> None:
    test_id = "CHAT-LIVE-02"
    dirs = ensure_test_artifact_dirs(artifact_root, test_id)
    ready, reason = _check_live_provider(page, api_base_url)
    if not ready:
        pytest.skip(reason)

    page.goto(base_url)
    page.get_by_label("Chat message").fill("Show me Rome")
    page.get_by_role("button", name="Send message").click()
    expect(page.locator(".chat-message--assistant").last).to_be_visible(timeout=60000)
    first_conversation_id = _read_conversation_id(page)
    assert first_conversation_id
    write_snapshot(page, dirs["screenshots"], "00-before-followup")

    page.get_by_label("Chat message").fill("Now zoom to nearby neighborhoods")
    page.get_by_role("button", name="Send message").click()
    write_snapshot(page, dirs["screenshots"], "01-live-followup")
    expect(page.locator(".chat-message--assistant").last).to_be_visible(timeout=60000)
    write_snapshot(page, dirs["screenshots"], "02-live-followup-response")
    second_conversation_id = _read_conversation_id(page)
    assert second_conversation_id == first_conversation_id

    tail = read_backend_log_tail(200)
    write_log_tail(dirs["logs"], test_id, tail)
    _assert_clean_backend_tail(tail)
    write_report(
        dirs["reports"],
        test_id,
        prompts=["Show me Rome", "Now zoom to nearby neighborhoods"],
        assertions=[
            "follow-up completed",
            "conversation continuity preserved",
            "no full reset occurred",
            "backend log tail clean",
        ],
        backend_log_status="clean" if tail.strip() else "empty",
    )


###############################################################################
def test_live_new_chat_reset(page: Page, base_url: str, api_base_url: str) -> None:
    ready, reason = _check_live_provider(page, api_base_url)
    if not ready:
        pytest.skip(reason)
    page.goto(base_url)
    page.get_by_label("Chat message").fill("Show me Rome")
    page.get_by_role("button", name="Send message").click()
    expect(page.locator(".chat-message--assistant").last).to_be_visible(timeout=60000)
    page.get_by_role("button", name="Start new chat").click()
    expect(page.get_by_text("Map Workspace")).to_be_visible()
    expect(page.locator(".overlay-controls")).not_to_be_visible()


###############################################################################
def test_live_degraded_path_shows_user_failure_without_crash(
    page: Page, base_url: str
) -> None:
    register_realtime_stub(
        page,
        lambda _message, _run_number: {},
        error_message="Provider unavailable for this test",
    )
    page.goto(base_url)
    page.get_by_label("Chat message").fill("Show me Rome")
    page.get_by_role("button", name="Send message").click()
    expect(page.locator(".chat-message--assistant").last).to_be_visible(timeout=15000)
    assistant_text = page.locator(
        ".chat-message--assistant .chat-message__content"
    ).last
    expect(assistant_text).to_contain_text(
        re.compile(r"provider unavailable|request failed|503", re.IGNORECASE)
    )
    expect(page.get_by_label("Chat message")).to_be_visible()
