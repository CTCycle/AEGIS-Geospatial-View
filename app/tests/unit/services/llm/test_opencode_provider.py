from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from server.services.llm.opencode_provider import (
    OPENCODE_GO_PROVIDER,
    OPENCODE_PROVIDER,
    OpenCodeProvider,
)
from server.services.llm.errors import LLMProviderRequestError
from server.services.llm.types import LLMRequest


###############################################################################
class _StructuredPayload(BaseModel):
    answer: str


###############################################################################
class _Response:
    # -------------------------------------------------------------------------
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    # -------------------------------------------------------------------------
    def raise_for_status(self) -> None:
        return None

    # -------------------------------------------------------------------------
    def json(self) -> dict[str, object]:
        return self.payload


###############################################################################
class _Completions:
    # -------------------------------------------------------------------------
    def __init__(self, error: Exception | None = None) -> None:
        self.calls: list[dict[str, object]] = []
        self.error = error

    # -------------------------------------------------------------------------
    def create(self, **kwargs):  # noqa: ANN003, ANN201
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        if kwargs.get("stream") is True:
            return [
                SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            delta=SimpleNamespace(content="streamed")
                        )
                    ]
                )
            ]
        message = SimpleNamespace(
            content=json.dumps({"answer": "structured"}),
            tool_calls=[],
        )
        return SimpleNamespace(
            choices=[SimpleNamespace(message=message, finish_reason="stop")]
        )


###############################################################################
class _Client:
    # -------------------------------------------------------------------------
    def __init__(self, error: Exception | None = None) -> None:
        self.completions = _Completions(error)
        self.chat = SimpleNamespace(completions=self.completions)
        self.timeout_options: list[dict[str, object]] = []

    # -------------------------------------------------------------------------
    def with_options(self, **kwargs):  # noqa: ANN003, ANN201
        self.timeout_options.append(kwargs)
        return self


###############################################################################
def test_zen_catalog_keeps_live_models_even_when_static_capabilities_are_unknown(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_get(url: str, **kwargs):  # noqa: ANN003, ANN202
        captured["url"] = url
        captured["kwargs"] = kwargs
        return _Response(
            {
                "data": [
                    {"id": "deepseek-v4-flash", "owned_by": "opencode"},
                    {"id": "claude-opus-5", "owned_by": "opencode"},
                ]
            }
        )

    monkeypatch.setattr("server.services.llm.opencode_provider.httpx.get", fake_get)
    provider = OpenCodeProvider(api_key="test-key", provider_name=OPENCODE_PROVIDER)

    models = provider.list_models()

    assert [model.name for model in models] == ["deepseek-v4-flash", "claude-opus-5"]
    assert models[0].provider == OPENCODE_PROVIDER
    assert models[0].metadata["protocol"] == "openai-chat-completions"
    assert models[1].capabilities == ["chat", "stream"]
    assert captured["url"] == "https://opencode.ai/zen/v1/models"
    assert captured["kwargs"]["headers"]["Authorization"] == "Bearer test-key"


###############################################################################
def test_go_uses_go_endpoint_and_exposes_tool_capabilities() -> None:
    provider = OpenCodeProvider(api_key="test-key", provider_name=OPENCODE_GO_PROVIDER)

    assert provider.base_url == "https://opencode.ai/zen/go/v1"
    assert provider.supports_tools("deepseek-v4-flash") is True
    assert provider.supports_structured_output("deepseek-v4-flash") is True
    assert provider.supports_tools("claude-opus-5") is None


###############################################################################
def test_structured_output_uses_chat_completions_json_object_mode(monkeypatch) -> None:
    client = _Client()
    provider = OpenCodeProvider(api_key="test-key", provider_name=OPENCODE_GO_PROVIDER)
    monkeypatch.setattr(provider, "_client", lambda: client)
    request = LLMRequest(
        model="deepseek-v4-flash",
        messages=[
            {"role": "system", "content": "Extract the answer."},
            {"role": "user", "content": "Hello"},
        ],
        metadata={"max_tokens": 123},
    )

    result = provider.structured_output(request, schema=_StructuredPayload)

    assert result == {"answer": "structured"}
    call = client.completions.calls[0]
    assert call["response_format"] == {"type": "json_object"}
    assert call["max_tokens"] == 123
    assert "JSON schema" in call["messages"][-1]["content"]
    assert result.context_usage["response_schema_tokens"] == 0


###############################################################################
def test_chat_forwards_bounded_output_tokens(monkeypatch) -> None:
    client = _Client()
    provider = OpenCodeProvider(api_key="test-key", provider_name=OPENCODE_GO_PROVIDER)
    monkeypatch.setattr(provider, "_client", lambda: client)
    request = LLMRequest(
        model="deepseek-v4-flash",
        messages=[{"role": "user", "content": "Hello"}],
        metadata={"max_tokens": 77},
    )

    provider.chat(request)

    assert client.completions.calls[0]["max_tokens"] == 77


###############################################################################
def test_stream_forwards_bounded_output_tokens(monkeypatch) -> None:
    client = _Client()
    provider = OpenCodeProvider(api_key="test-key", provider_name=OPENCODE_GO_PROVIDER)
    monkeypatch.setattr(provider, "_client", lambda: client)
    request = LLMRequest(
        model="deepseek-v4-flash",
        messages=[{"role": "user", "content": "Hello"}],
        metadata={"max_tokens": 88},
    )

    assert list(provider.stream_chat(request)) == ["streamed"]
    assert client.completions.calls[0]["max_tokens"] == 88


###############################################################################
def test_bounded_deadline_is_forwarded_without_the_old_thirty_second_cap(
    monkeypatch,
) -> None:
    client = _Client()
    provider = OpenCodeProvider(api_key="test-key", provider_name=OPENCODE_GO_PROVIDER)
    monkeypatch.setattr(provider, "_client", lambda: client)
    monkeypatch.setattr(
        "server.services.llm.deepseek_provider.remaining_request_seconds",
        lambda request: 47.5,
    )

    provider._client_for_request(
        LLMRequest(
            model="deepseek-v4-flash",
            messages=[{"role": "user", "content": "Hello"}],
        )
    )

    assert client.timeout_options == [{"timeout": 47.5}]


###############################################################################
def test_timeout_failure_keeps_preflight_context_usage(monkeypatch) -> None:
    client = _Client(TimeoutError("completion timed out"))
    provider = OpenCodeProvider(api_key="test-key", provider_name=OPENCODE_GO_PROVIDER)
    monkeypatch.setattr(provider, "_client", lambda: client)
    request = LLMRequest(
        model="deepseek-v4-flash",
        messages=[{"role": "user", "content": "Hello"}],
        metadata={"max_tokens": 123},
    )

    with pytest.raises(LLMProviderRequestError) as error:
        provider.structured_output(request, schema=_StructuredPayload)

    assert error.value.code == "provider_timeout"
    assert error.value.retryable is False
    assert error.value.context_usage is not None
    assert error.value.context_usage["estimated_input_tokens"] > 0
    assert error.value.context_usage["response_schema_tokens"] == 0
