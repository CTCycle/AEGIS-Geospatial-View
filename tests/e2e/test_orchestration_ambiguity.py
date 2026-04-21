from __future__ import annotations

import pytest
from playwright.sync_api import APIRequestContext


def _turn(api_context: APIRequestContext, message: str, session_id: int | None = None):
    payload = {"message": message}
    if session_id is not None:
        payload["session_id"] = session_id
    response = api_context.post("/api/chat/turn", data=payload)
    if response.status in {400, 502, 503}:
        pytest.skip(
            f"Provider unavailable for orchestration check ({response.status})."
        )
    assert response.ok, f"Expected 200, got {response.status}"
    body = response.json()
    if body.get("fallback_mode") == "provider_unavailable":
        pytest.skip("Provider unavailable for orchestration check (fallback mode).")
    return body


def test_ambiguous_temporal_request_produces_clarification(
    api_context: APIRequestContext,
) -> None:
    body = _turn(api_context, "Show me weather")
    assert body.get("follow_up_required") is True
    assert body.get("map_session") is None


def test_missing_location_produces_clarification_or_validation(
    api_context: APIRequestContext,
) -> None:
    body = _turn(api_context, "Show me air quality overlays")
    if body.get("follow_up_required") is True:
        return
    assistant = str(body.get("assistant_message") or "").lower()
    assert "location" in assistant or "where" in assistant


def test_direct_coordinates_request_does_not_create_map_session(
    api_context: APIRequestContext,
) -> None:
    body = _turn(api_context, "Give me the coordinates of the Eiffel Tower")
    assert body.get("map_session") is None
    assistant = str(body.get("assistant_message") or "")
    assert "latitude" in assistant.lower() or "coordinates" in assistant.lower()


def test_runtime_overlay_request_reply_does_not_leak_internal_tool_ids(
    api_context: APIRequestContext,
) -> None:
    body = _turn(api_context, "Show traffic in Rome with map overlays")
    assistant = str(body.get("assistant_message") or "")
    assert "tool_" not in assistant.lower()
    assert "internal id" not in assistant.lower()


def test_missing_key_request_clarifies_or_falls_back_consistently(
    api_context: APIRequestContext,
) -> None:
    body = _turn(api_context, "Use TomTom traffic in Rome")
    assistant = str(body.get("assistant_message") or "").lower()
    if body.get("follow_up_required") is True:
        assert (
            "key" in assistant or "configure" in assistant or "alternative" in assistant
        )
        return
    assert "traffic" in assistant or "map search" in assistant
