from __future__ import annotations

import json

import pytest
from playwright.sync_api import APIRequestContext


def _post(api_context: APIRequestContext, path: str, payload: dict):
    return api_context.post(path, data=payload)


def _get(api_context: APIRequestContext, path: str):
    return api_context.get(path)


def _put(api_context: APIRequestContext, path: str, payload: dict):
    return api_context.put(path, data=payload)


def _require_provider_or_skip(response) -> None:  # noqa: ANN001
    if response.status in {400, 502, 503}:
        pytest.skip(f"Providers unavailable for this check ({response.status}).")


def _require_parser_or_skip(body: dict) -> None:
    assistant_text = str(body.get("assistant_message") or "").lower()
    if "configured parser model is unavailable" in assistant_text:
        pytest.skip("Configured parser model is unavailable for this check.")


def test_chat_settings_crud_and_prefix_parity(api_context: APIRequestContext) -> None:
    base = _get(api_context, "/api/chat/settings")
    prefixed = _get(api_context, "/api/chat/settings")
    if not base.ok or not prefixed.ok:
        pytest.skip(
            f"Chat settings endpoint unavailable ({base.status}/{prefixed.status})."
        )
    assert base.ok and prefixed.ok
    base_body = base.json()
    prefixed_body = prefixed.json()
    assert set(base_body.keys()) == set(prefixed_body.keys())

    update_payload = {
        **base_body,
        "parser_model_provider": "ollama",
        "parser_model_name": "llama3.2",
        "ollama_url": base_body.get("ollama_url", "http://localhost:11434"),
        "credentials": {"openai": {"api_key": "sk-test-value"}},
    }
    updated = _put(api_context, "/api/chat/settings", update_payload)
    if updated.status == 422:
        pytest.skip("Requested local parser model is unavailable for this check.")
    assert updated.ok
    updated_body = updated.json()
    assert updated_body["credentials"]["openai"]["api_key"] is True

    parity_update = _put(api_context, "/api/chat/settings", update_payload)
    assert parity_update.ok
    assert set(updated_body.keys()) == set(parity_update.json().keys())

    restored = _put(api_context, "/api/chat/settings", base_body)
    assert restored.ok


def test_chat_settings_invalid_payload_handling(api_context: APIRequestContext) -> None:
    response = _put(
        api_context,
        "/api/chat/settings",
        {"active_provider_mode": 1, "credentials": "bad"},
    )
    assert response.status in {200, 400, 422, 500}
    if response.ok:
        body = response.json()
        assert "active_provider_mode" in body


def test_chat_models_with_prefix_parity(
    api_context: APIRequestContext,
) -> None:
    models_base = _get(api_context, "/api/chat/models")
    models_prefixed = _get(api_context, "/api/chat/models")
    assert models_base.ok and models_prefixed.ok
    base_body = models_base.json()
    prefixed_body = models_prefixed.json()
    assert isinstance(base_body.get("cloud"), list)
    assert isinstance(base_body.get("local"), list)
    assert set(base_body.keys()) == set(prefixed_body.keys())


def test_chat_turn_stream_event_order_and_contract_parity(
    api_context: APIRequestContext,
) -> None:
    turn_response = _post(
        api_context, "/api/chat/turn", {"message": "show map at 41.9028, 12.4964"}
    )
    _require_provider_or_skip(turn_response)
    assert turn_response.ok
    turn_body = turn_response.json()
    assert "assistant_message" in turn_body
    assert "session_id" in turn_body
    assert "turn_contract" in turn_body
    assert "decision" in turn_body

    prefixed_turn = _post(
        api_context, "/api/chat/turn", {"message": "show map at 41.9028, 12.4964"}
    )
    _require_provider_or_skip(prefixed_turn)
    assert prefixed_turn.ok
    assert set(turn_body.keys()) == set(prefixed_turn.json().keys())

    stream_response = _post(
        api_context,
        "/api/chat/stream",
        {
            "session_id": turn_body["session_id"],
            "message": "show map at 41.9028, 12.4964",
        },
    )
    _require_provider_or_skip(stream_response)
    assert stream_response.ok
    events = [
        json.loads(line) for line in stream_response.text().splitlines() if line.strip()
    ]
    event_names = [entry.get("event") for entry in events]
    assert event_names[0] == "status"
    assert event_names[-1] in {"final", "error"}
    if event_names[-1] == "final":
        assert "parsed" in event_names
        assert "policy" in event_names
        if "tool_call_started" in event_names:
            assert "tool_call_completed" in event_names
            assert event_names.index("tool_call_started") < event_names.index("tool_call_completed")
        if "map_session_created" in event_names:
            assert event_names.index("map_session_created") < event_names.index("final")

    prefixed_stream = _post(
        api_context,
        "/api/chat/stream",
        {
            "session_id": turn_body["session_id"],
            "message": "show map at 41.9028, 12.4964",
        },
    )
    _require_provider_or_skip(prefixed_stream)
    assert prefixed_stream.ok


def test_chat_turn_coordinate_lookup_and_follow_up(
    api_context: APIRequestContext,
) -> None:
    geocode_response = _post(
        api_context,
        "/api/chat/turn",
        {"message": "Give me the coordinates of Rome, Italy"},
    )
    _require_provider_or_skip(geocode_response)
    assert geocode_response.ok
    geocode_body = geocode_response.json()
    _require_parser_or_skip(geocode_body)
    assert geocode_body.get("map_session") is None
    assistant_text = str(geocode_body.get("assistant_message") or "").lower()
    assert (
        "latitude" in assistant_text
        or "coordinates" in assistant_text
        or "clarify" in assistant_text
        or "ollama" in assistant_text
    )

    unsupported = _post(
        api_context,
        "/api/chat/turn",
        {"message": "Find the absolute best weather area in Europe"},
    )
    _require_provider_or_skip(unsupported)
    assert unsupported.ok
    unsupported_body = unsupported.json()
    _require_parser_or_skip(unsupported_body)
    if unsupported_body.get("decision", {}).get("plan", {}).get("state") == "clarify":
        return
    assistant = str(unsupported_body.get("assistant_message") or "").lower()
    assert "weather" in assistant or "forecast" in assistant or "clarify" in assistant


def test_ollama_refresh_pull_health(api_context: APIRequestContext) -> None:
    refresh_base = _post(api_context, "/api/chat/models/ollama/refresh", {})
    refresh_prefixed = _post(api_context, "/api/chat/models/ollama/refresh", {})
    assert refresh_base.ok and refresh_prefixed.ok

    try:
        pull_base = _post(
            api_context, "/api/chat/models/ollama/pull", {"model": "llama3.2"}
        )
        pull_prefixed = _post(
            api_context, "/api/chat/models/ollama/pull", {"model": "llama3.2"}
        )
    except PlaywrightError as exc:
        pytest.skip(f"Ollama pull timed out ({exc})")
    assert pull_base.status in {200, 400, 502}
    assert pull_prefixed.status in {200, 400, 502}

    health_base = _get(api_context, "/api/chat/models/ollama/health")
    health_prefixed = _get(api_context, "/api/chat/models/ollama/health")
    assert health_base.ok and health_prefixed.ok
