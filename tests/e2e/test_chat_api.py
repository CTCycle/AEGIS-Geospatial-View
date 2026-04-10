from __future__ import annotations

import pytest
from playwright.sync_api import APIRequestContext


def test_chat_settings_crud(api_context: APIRequestContext) -> None:
    get_response = api_context.get("/chat/settings")
    assert get_response.ok, f"Expected 200, got {get_response.status}"
    body = get_response.json()
    assert "active_provider_mode" in body
    assert "parser_model_provider" in body
    assert "parser_model_name" in body

    put_response = api_context.put(
        "/chat/settings",
        data={
            **body,
            "parser_model_provider": "ollama",
            "parser_model_name": "llama3.2",
            "ollama_url": body.get("ollama_url", "http://localhost:11434"),
            "credentials": {"openai": {"api_key": "sk-test-value"}},
        },
    )
    assert put_response.ok, f"Expected 200, got {put_response.status}"
    updated = put_response.json()
    assert "credentials" in updated
    assert updated["credentials"].get("openai", {}).get("api_key") is True
    assert updated.get("parser_model_provider") == "ollama"


def test_chat_models_and_vector_rebuild(api_context: APIRequestContext) -> None:
    models_response = api_context.get("/chat/models")
    assert models_response.ok, f"Expected 200, got {models_response.status}"
    models_body = models_response.json()
    assert isinstance(models_body.get("cloud"), list)
    assert isinstance(models_body.get("local"), list)

    sync_response = api_context.post("/chat/vectors/sync")
    assert sync_response.ok, f"Expected 200, got {sync_response.status}"
    sync_body = sync_response.json()
    assert "indexed_documents" in sync_body

    vector_response = api_context.post("/chat/vectors/rebuild")
    assert vector_response.ok, f"Expected 200, got {vector_response.status}"
    vector_body = vector_response.json()
    assert vector_body.get("indexed_documents", 0) > 0


def test_chat_turn_and_stream(api_context: APIRequestContext) -> None:
    geocode_response = api_context.post(
        "/chat/turn",
        data={"message": "Give me the coordinates of Rome, Italy"},
    )
    if geocode_response.status in {400, 502}:
        pytest.skip("Providers unavailable for geocode request check.")
    assert geocode_response.ok, f"Expected 200, got {geocode_response.status}"
    geocode_body = geocode_response.json()
    assert geocode_body.get("map_session") is None
    assistant_text = str(geocode_body.get("assistant_message") or "")
    assert "latitude" in assistant_text.lower() or "coordinates" in assistant_text.lower()
    assert "overlay_ids" not in assistant_text
    assert "gibs_layer_" not in assistant_text
    assert "{" not in assistant_text

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
    assert "extracted_state" in turn_body

    reuse_response = api_context.post(
        "/chat/turn",
        data={"session_id": turn_body["session_id"], "message": "use same session near Rome"},
    )
    if reuse_response.status in {400, 502}:
        pytest.skip("Search providers unavailable for session reuse.")
    assert reuse_response.ok, f"Expected 200, got {reuse_response.status}"
    reuse_body = reuse_response.json()
    assert reuse_body.get("session_id") == turn_body["session_id"]
    assert "Unable to resolve map extent for the requested imagery." not in reuse_body.get(
        "assistant_message", ""
    )

    unsupported_response = api_context.post(
        "/chat/turn",
        data={"message": "Find the absolute best weather area in Europe"},
    )
    if unsupported_response.status in {400, 502}:
        pytest.skip("Search providers unavailable for unsupported request check.")
    assert unsupported_response.ok, f"Expected 200, got {unsupported_response.status}"
    unsupported_body = unsupported_response.json()
    assert unsupported_body.get("follow_up_required") is True

    stream_response = api_context.post(
        "/chat/stream",
        data={"session_id": turn_body["session_id"], "message": "show map at 41.9028, 12.4964"},
    )
    if stream_response.status in {400, 502}:
        pytest.skip("Search providers unavailable for chat stream.")
    assert stream_response.ok, f"Expected 200, got {stream_response.status}"
    stream_text = stream_response.text()
    assert '"event": "final"' in stream_text
    assert '"extracted_state"' in stream_text


def test_ollama_refresh_pull_health(api_context: APIRequestContext) -> None:
    refresh = api_context.post("/chat/models/ollama/refresh")
    assert refresh.ok, f"Expected 200, got {refresh.status}"

    pull = api_context.post("/chat/models/ollama/pull", data={"model": "llama3.2"})
    assert pull.status in {200, 400, 502}

    health = api_context.get("/chat/models/ollama/health")
    assert health.ok, f"Expected 200, got {health.status}"
