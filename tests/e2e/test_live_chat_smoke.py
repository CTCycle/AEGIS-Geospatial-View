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


def _check_live_provider(page: Page, api_base_url: str) -> tuple[bool, str]:
    response = page.request.post(
        f"{api_base_url.rstrip('/')}/api/chat/turn",
        data={"message": "Give me the coordinates of Rome, Italy"},
    )
    if response.status == 200:
        return True, ""
    if response.status in {400, 502, 503}:
        return False, f"Live provider precondition failed with status {response.status}"
    return False, f"Unexpected provider precondition status {response.status}"


def _assert_clean_backend_tail(tail: str) -> None:
    normalized = tail.lower()
    assert "traceback" not in normalized
    assert "unhandled exception" not in normalized


def _read_session_id(page: Page) -> int | None:
    raw = page.evaluate("() => window.sessionStorage.getItem('aegis:webapp-state:v2')")
    if not raw:
        return None
    data = json.loads(raw)
    return data.get("chatPage", {}).get("chatPanel", {}).get("sessionId")


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
    page.get_by_role("button", name="Send").click()
    write_snapshot(page, dirs["screenshots"], "01-live-request")
    expect(page.locator(".chat-message--assistant").last).to_be_visible(timeout=60000)
    write_snapshot(page, dirs["screenshots"], "02-live-response")

    session_id = _read_session_id(page)
    assert isinstance(session_id, int) and session_id > 0

    tail = read_backend_log_tail(200)
    write_log_tail(dirs["logs"], test_id, tail)
    _assert_clean_backend_tail(tail)
    write_http_capture(
        dirs["http"], "turn-01", {"message": "Show me Rome"}, {"session_id": session_id}
    )
    write_report(
        dirs["reports"],
        test_id,
        prompts=["Show me Rome"],
        assertions=[
            "assistant response rendered",
            "session id persisted",
            "backend log tail clean",
        ],
        backend_log_status="clean" if tail.strip() else "empty",
    )


def test_live_follow_up_same_session(
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
    page.get_by_role("button", name="Send").click()
    expect(page.locator(".chat-message--assistant").last).to_be_visible(timeout=60000)
    first_session_id = _read_session_id(page)
    write_snapshot(page, dirs["screenshots"], "00-before-followup")

    page.get_by_label("Chat message").fill("Now zoom to nearby neighborhoods")
    page.get_by_role("button", name="Send").click()
    write_snapshot(page, dirs["screenshots"], "01-live-followup")
    expect(page.locator(".chat-message--assistant").last).to_be_visible(timeout=60000)
    write_snapshot(page, dirs["screenshots"], "02-live-followup-response")
    second_session_id = _read_session_id(page)
    assert first_session_id == second_session_id

    tail = read_backend_log_tail(200)
    write_log_tail(dirs["logs"], test_id, tail)
    _assert_clean_backend_tail(tail)
    write_report(
        dirs["reports"],
        test_id,
        prompts=["Show me Rome", "Now zoom to nearby neighborhoods"],
        assertions=[
            "follow-up completed",
            "session continuity preserved",
            "no full reset occurred",
            "backend log tail clean",
        ],
        backend_log_status="clean" if tail.strip() else "empty",
    )


def test_live_new_chat_reset(page: Page, base_url: str, api_base_url: str) -> None:
    ready, reason = _check_live_provider(page, api_base_url)
    if not ready:
        pytest.skip(reason)
    page.goto(base_url)
    page.get_by_label("Chat message").fill("Show me Rome")
    page.get_by_role("button", name="Send").click()
    expect(page.locator(".chat-message--assistant").last).to_be_visible(timeout=60000)
    page.get_by_role("button", name="Start new chat").click()
    expect(page.get_by_text("Enter a location-based request to begin.")).to_be_visible()
    expect(page.locator(".overlay-controls")).not_to_be_visible()


def test_live_degraded_path_shows_user_failure_without_crash(
    page: Page, base_url: str
) -> None:
    page.route(
        "**/api/chat/turn",
        lambda route: route.fulfill(
            status=503,
            content_type="application/json",
            body=json.dumps({"detail": "Provider unavailable for this test"}),
        ),
    )
    page.route(
        "**/api/chat/turn",
        lambda route: route.fulfill(
            status=503,
            content_type="application/json",
            body=json.dumps({"detail": "Provider unavailable for this test"}),
        ),
    )
    page.goto(base_url)
    page.get_by_label("Chat message").fill("Show me Rome")
    page.get_by_role("button", name="Send").click()
    expect(page.locator(".chat-message--assistant").last).to_be_visible(timeout=15000)
    assistant_text = page.locator(".chat-message--assistant .chat-message__content").last
    expect(assistant_text).to_contain_text(
        re.compile(r"provider unavailable|request failed|503", re.IGNORECASE)
    )
    expect(page.get_by_label("Chat message")).to_be_visible()
