from __future__ import annotations

import pytest
from playwright.sync_api import APIRequestContext


def test_chat_settings_crud(api_context: APIRequestContext) -> None:
    get_response = api_context.get("/chat/settings")
    assert get_response.ok, f"Expected 200, got {get_response.status}"
    body = get_response.json()
    assert "active_provider_mode" in body

    put_response = api_context.put(
        "/chat/settings",
        data={
            **body,
            "ollama_url": body.get("ollama_url", "http://localhost:11434"),
            "credentials": {"openai": {"api_key": "sk-test-value"}},
        },
    )
    assert put_response.ok, f"Expected 200, got {put_response.status}"
    updated = put_response.json()
    assert "credentials" in updated
    assert updated["credentials"].get("openai", {}).get("api_key") is True


def test_chat_models_and_vector_rebuild(api_context: APIRequestContext) -> None:
    models_response = api_context.get("/chat/models")
    assert models_response.ok, f"Expected 200, got {models_response.status}"
    models_body = models_response.json()
    assert isinstance(models_body.get("cloud"), list)
    assert isinstance(models_body.get("local"), list)

    vector_response = api_context.post("/chat/vectors/rebuild")
    assert vector_response.ok, f"Expected 200, got {vector_response.status}"
    vector_body = vector_response.json()
    assert vector_body.get("indexed_documents", 0) > 0


def test_chat_turn_and_stream(api_context: APIRequestContext) -> None:
    turn_response = api_context.post(
        "/chat/turn",
        data={"message": "show map at 41.9028, 12.4964"},
    )
    if turn_response.status in {400, 502}:
        pytest.skip("Search providers unavailable for chat turn.")
    assert turn_response.ok, f"Expected 200, got {turn_response.status}"
    turn_body = turn_response.json()
    assert "assistant_message" in turn_body
    assert "session_id" in turn_body

    stream_response = api_context.post(
        "/chat/stream",
        data={"session_id": turn_body["session_id"], "message": "show map at 41.9028, 12.4964"},
    )
    if stream_response.status in {400, 502}:
        pytest.skip("Search providers unavailable for chat stream.")
    assert stream_response.ok, f"Expected 200, got {stream_response.status}"
    stream_text = stream_response.text()
    assert '"event": "final"' in stream_text


def test_ollama_refresh_pull_health(api_context: APIRequestContext) -> None:
    refresh = api_context.post("/chat/models/ollama/refresh")
    assert refresh.ok, f"Expected 200, got {refresh.status}"

    pull = api_context.post("/chat/models/ollama/pull", data={"model": "llama3.2"})
    assert pull.status in {200, 400, 502}

    health = api_context.get("/chat/models/ollama/health")
    assert health.ok, f"Expected 200, got {health.status}"
