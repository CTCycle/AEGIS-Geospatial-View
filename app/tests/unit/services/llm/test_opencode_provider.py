from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import pytest
from pydantic import BaseModel

from server.services.llm.opencode_provider import (
    OPENCODE_GO_PROVIDER,
    OPENCODE_PROVIDER,
    OpenCodeProvider,
)
from server.services.llm.errors import LLMProviderRequestError, LLMResponseParsingError
from server.services.llm.opencode_messages_transport import build_messages_payload
from server.services.llm.opencode_models_dev import ModelsDevEntry
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
        if kwargs.get("tools"):
            message = SimpleNamespace(
                content=None,
                tool_calls=[
                    SimpleNamespace(
                        id="structured-call",
                        function=SimpleNamespace(
                            name="submit_structured_response",
                            arguments=json.dumps({"answer": "structured"}),
                        ),
                    )
                ],
            )
        else:
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
    assert "tools" in models[1].capabilities
    assert models[1].metadata["protocol"] == "anthropic-messages"
    assert captured["url"] == "https://opencode.ai/zen/v1/models"
    assert captured["kwargs"]["headers"]["Authorization"] == "Bearer test-key"
    assert captured["kwargs"]["headers"]["User-Agent"] == "AEGIS-Geospatial-View/1.0.0"

###############################################################################
def test_go_uses_go_endpoint_and_exposes_tool_capabilities() -> None:
    provider = OpenCodeProvider(api_key="test-key", provider_name=OPENCODE_GO_PROVIDER)

    assert provider.base_url == "https://opencode.ai/zen/go/v1"
    assert provider.protocol_for_model("deepseek-v4.1-flash") == "openai-chat-completions"
    assert provider.supports_tools("deepseek-v4.1-flash") is True
    assert provider.supports_structured_output("deepseek-v4.1-flash") is True
    assert provider.supports_tools("deepseek-v4-flash") is True
    assert provider.supports_structured_output("deepseek-v4-flash") is True
    assert provider.supports_tools("minimax-m3") is True

###############################################################################
def test_go_catalog_marks_deepseek_v41_flash_as_live_chat_model(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_get(url: str, **kwargs):  # noqa: ANN003, ANN202
        captured["url"] = url
        captured["kwargs"] = kwargs
        return _Response(
            {
                "object": "list",
                "data": [
                    {"id": "deepseek-v4.1-flash", "owned_by": "opencode"},
                    {"id": "model-published-without-a-transport"},
                ],
            }
        )

    monkeypatch.setattr("server.services.llm.opencode_provider.httpx.get", fake_get)
    provider = OpenCodeProvider(api_key="test-key", provider_name=OPENCODE_GO_PROVIDER)

    models = provider.list_models()

    assert [model.name for model in models] == [
        "deepseek-v4.1-flash",
        "model-published-without-a-transport",
    ]
    selected = models[0]
    assert selected.provider == OPENCODE_GO_PROVIDER
    assert selected.metadata["protocol"] == "openai-chat-completions"
    assert selected.metadata["protocol_source"] == "opencode_published_endpoint_table"
    assert "tools" in selected.capabilities
    assert "structured_output" in selected.capabilities
    assert models[1].metadata["protocol"] == "openai-chat-completions"
    assert models[1].metadata["protocol_source"] == "assumed_default"
    assert "tools" in models[1].capabilities
    assert captured["url"] == "https://opencode.ai/zen/go/v1/models"


###############################################################################
def test_models_dev_publishes_protocol_limits_and_vision_for_unlisted_models(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "server.services.llm.opencode_provider.fetch_models_dev_entries",
        lambda provider, policy: {
            "gpt-6-luna": ModelsDevEntry(
                "openai-responses", 1_050_000, 128_000, True
            ),
            "qwen3.8-max": ModelsDevEntry(
                "anthropic-messages", 1_000_000, 131_072, True
            ),
        },
    )
    monkeypatch.setattr(
        "server.services.llm.opencode_provider.httpx.get",
        lambda url, **kwargs: _Response(
            {"data": [{"id": "gpt-6-luna"}, {"id": "qwen3.8-max"}]}
        ),
    )
    provider = OpenCodeProvider(api_key="test-key", provider_name=OPENCODE_GO_PROVIDER)

    luna, qwen = provider.list_models()

    assert luna.metadata["protocol"] == "openai-responses"
    assert luna.metadata["protocol_source"] == "models_dev"
    assert luna.metadata["context_window_tokens"] == 1_050_000
    assert luna.metadata["maximum_output_tokens"] == 128_000
    assert luna.metadata["supports_vision"] is True
    assert qwen.metadata["protocol"] == "anthropic-messages"
    assert provider.protocol_for_model("gpt-6-luna") == "openai-responses"

###############################################################################
def test_protocol_lookup_consults_models_dev_without_a_catalog_listing(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "server.services.llm.opencode_provider.fetch_models_dev_entries",
        lambda provider, policy: {
            "grok-4.7": ModelsDevEntry("openai-responses", None, None, False)
        },
    )
    provider = OpenCodeProvider(api_key="test-key", provider_name=OPENCODE_GO_PROVIDER)

    assert provider.protocol_for_model("grok-4.7") == "openai-responses"

###############################################################################
def test_opencode_normalizes_nested_documented_limits(monkeypatch) -> None:
    def fake_get(url: str, **kwargs):  # noqa: ANN001, ARG001
        return _Response(
            {
                "data": [
                    {
                        "id": "runtime-model",
                        "owned_by": "opencode",
                        "limit": {"context": 32_768, "output": 4096},
                    }
                ]
            }
        )

    monkeypatch.setattr("server.services.llm.opencode_provider.httpx.get", fake_get)
    model = OpenCodeProvider(
        api_key="test-key", provider_name=OPENCODE_PROVIDER
    ).list_models()[0]

    assert model.metadata["context_window_tokens"] == 32_768
    assert model.metadata["maximum_output_tokens"] == 4096
    assert model.metadata["context_metadata_authority"] == "provider"

###############################################################################
def test_structured_output_uses_single_function_mode(monkeypatch) -> None:
    client = _Client()
    provider = OpenCodeProvider(api_key="test-key", provider_name=OPENCODE_GO_PROVIDER)
    monkeypatch.setattr(
        provider,
        "_client",
        lambda _request=None, **_kwargs: client,
    )
    request = LLMRequest(
        model="deepseek-v4-flash",
        provider_session_id="conversation-1",
        messages=[
            {"role": "system", "content": "Extract the answer."},
            {"role": "user", "content": "Hello"},
        ],
        metadata={"max_tokens": 123},
    )

    result = provider.structured_output(request, schema=_StructuredPayload)

    assert result == {"answer": "structured"}
    call = client.completions.calls[0]
    assert len(call["tools"]) == 1
    assert call["tools"][0]["function"]["name"] == "submit_structured_response"
    assert call["tools"][0]["function"]["parameters"] == _StructuredPayload.model_json_schema()
    assert "response_format" not in call
    assert "tool_choice" not in call
    assert call["max_tokens"] == 123
    assert result.context_usage["response_schema_tokens"] == 0

###############################################################################
def test_structured_output_forwards_explicit_thinking_mode(monkeypatch) -> None:
    client = _Client()
    provider = OpenCodeProvider(api_key="test-key", provider_name=OPENCODE_GO_PROVIDER)
    monkeypatch.setattr(
        provider,
        "_client",
        lambda _request=None, **_kwargs: client,
    )
    request = LLMRequest(
        model="deepseek-v4-flash",
        provider_session_id="conversation-1",
        messages=[{"role": "user", "content": "Hello"}],
        metadata={"thinking_mode": "disabled"},
    )

    provider.structured_output(request, schema=_StructuredPayload)

    assert client.completions.calls[0]["extra_body"] == {
        "thinking": {"type": "disabled"}
    }

###############################################################################
def test_chat_forwards_bounded_output_tokens(monkeypatch) -> None:
    client = _Client()
    provider = OpenCodeProvider(api_key="test-key", provider_name=OPENCODE_GO_PROVIDER)
    monkeypatch.setattr(
        provider,
        "_client",
        lambda _request=None, **_kwargs: client,
    )
    request = LLMRequest(
        model="deepseek-v4-flash",
        provider_session_id="conversation-1",
        messages=[{"role": "user", "content": "Hello"}],
        metadata={"max_tokens": 77},
    )

    provider.chat(request)

    assert client.completions.calls[0]["max_tokens"] == 77

###############################################################################
def test_stream_forwards_bounded_output_tokens(monkeypatch) -> None:
    client = _Client()
    provider = OpenCodeProvider(api_key="test-key", provider_name=OPENCODE_GO_PROVIDER)
    monkeypatch.setattr(
        provider,
        "_client",
        lambda _request=None, **_kwargs: client,
    )
    request = LLMRequest(
        model="deepseek-v4-flash",
        provider_session_id="conversation-1",
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
    monkeypatch.setattr(
        provider,
        "_client",
        lambda _request=None, **_kwargs: client,
    )
    monkeypatch.setattr(
        "server.services.llm.deepseek_provider.remaining_request_seconds",
        lambda request: 47.5,
    )

    provider._client_for_request(
        LLMRequest(
            model="deepseek-v4-flash",
            provider_session_id="conversation-1",
            messages=[{"role": "user", "content": "Hello"}],
        )
    )

    assert client.timeout_options == [{"timeout": 47.5}]

###############################################################################
def test_timeout_failure_keeps_preflight_context_usage(monkeypatch) -> None:
    client = _Client(TimeoutError("completion timed out"))
    provider = OpenCodeProvider(api_key="test-key", provider_name=OPENCODE_GO_PROVIDER)
    monkeypatch.setattr(
        provider,
        "_client",
        lambda _request=None, **_kwargs: client,
    )
    request = LLMRequest(
        model="deepseek-v4-flash",
        provider_session_id="conversation-1",
        messages=[{"role": "user", "content": "Hello"}],
        metadata={"max_tokens": 123},
    )

    with pytest.raises(LLMProviderRequestError) as error:
        provider.structured_output(request, schema=_StructuredPayload)

    assert error.value.code == "structured_timeout"
    assert error.value.retryable is False
    assert error.value.context_usage is not None
    assert error.value.context_usage["estimated_input_tokens"] > 0
    assert error.value.context_usage["response_schema_tokens"] == 0

###############################################################################
def test_opencode_session_headers_are_stable_per_conversation_and_not_shared() -> None:
    provider = OpenCodeProvider(api_key="test-key", provider_name=OPENCODE_GO_PROVIDER)

    first = provider._request_headers(
        LLMRequest(
            model="deepseek-v4-flash",
            messages=[],
            provider_session_id="conversation-a",
        )
    )
    retry = provider._request_headers(
        LLMRequest(
            model="deepseek-v4-flash",
            messages=[],
            provider_session_id="conversation-a",
        )
    )
    second = provider._request_headers(
        LLMRequest(
            model="deepseek-v4-flash",
            messages=[],
            provider_session_id="conversation-b",
        )
    )

    assert first == retry
    assert first["x-opencode-session"] == "conversation-a"
    assert second["x-opencode-session"] == "conversation-b"
    assert first["User-Agent"] == "AEGIS-Geospatial-View/1.0.0"
    assert "Authorization" not in first

###############################################################################
def test_opencode_requires_session_context_for_inference() -> None:
    provider = OpenCodeProvider(api_key="test-key", provider_name=OPENCODE_GO_PROVIDER)

    with pytest.raises(LLMProviderRequestError) as error:
        provider._request_headers(
            LLMRequest(model="deepseek-v4-flash", messages=[])
        )

    assert error.value.code == "provider_session_required"
    assert "test-key" not in str(error.value)

###############################################################################
def test_opencode_routes_responses_models_to_responses_transport(monkeypatch) -> None:
    captured: dict[str, object] = {}

    ###############################################################################
    class _Responses:

        # -------------------------------------------------------------------------
        def structured_output(self, request, schema):  # noqa: ANN001
            captured["request"] = request
            captured["schema"] = schema
            return {"answer": "responses"}

    provider = OpenCodeProvider(api_key="test-key", provider_name=OPENCODE_GO_PROVIDER)
    monkeypatch.setattr(provider, "_responses", lambda: _Responses())
    request = LLMRequest(
        model="gpt-5.6-luna",
        messages=[{"role": "user", "content": "Hello"}],
        provider_session_id="conversation-responses",
    )

    assert provider.structured_output(request, schema=_StructuredPayload) == {
        "answer": "responses"
    }
    routed = captured["request"]
    assert routed.provider == OPENCODE_GO_PROVIDER
    assert routed.provider_session_id == "conversation-responses"
    assert routed.metadata["protocol"] == "openai-responses"
    assert routed.metadata["supports_temperature"] is False

###############################################################################
def test_opencode_rejects_unimplemented_transport_without_guessing() -> None:
    provider = OpenCodeProvider(api_key="test-key", provider_name=OPENCODE_PROVIDER)
    request = LLMRequest(
        model="gemini-3.7-flash",
        messages=[{"role": "user", "content": "Hello"}],
        provider_session_id="conversation-messages",
    )

    with pytest.raises(LLMProviderRequestError) as error:
        provider.structured_output(request, schema=_StructuredPayload)

    assert error.value.code == "provider_transport_unsupported"

###############################################################################
def test_opencode_structured_wrapper_rejects_multiple_payloads() -> None:
    provider = OpenCodeProvider(api_key="test-key", provider_name=OPENCODE_GO_PROVIDER)
    function = SimpleNamespace(
        name="submit_structured_response",
        arguments=json.dumps({"answer": "structured"}),
    )
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content='{"answer":"duplicate"}',
                    tool_calls=[SimpleNamespace(id="one", function=function)],
                )
            )
        ]
    )

    with pytest.raises(LLMResponseParsingError) as error:
        provider._parse_structured_payload(  # pyright: ignore[reportPrivateUsage]
            response,
            _StructuredPayload,
            LLMRequest(
                model="deepseek-v4-flash",
                provider_session_id="conversation-1",
                messages=[],
            ),
            SimpleNamespace(to_dict=lambda: {}),
        )

    assert error.value.code == "structured_invalid_payload"

###############################################################################
def test_messages_payload_maps_tools_images_and_turn_roles() -> None:
    payload = build_messages_payload(
        model="qwen3.8-max",
        temperature=1.7,
        max_tokens=99,
        tool_choice="required",
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "lookup",
                    "description": "Look up.",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ],
        messages=[
            {"role": "system", "content": "Be brief."},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "See"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,QUJD"}},
                ],
            },
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {"name": "lookup", "arguments": '{"q": 1}'},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call-1", "content": "found"},
        ],
    )

    assert payload["system"] == "Be brief."
    assert payload["max_tokens"] == 99
    assert payload["temperature"] == 1.0
    assert payload["tool_choice"] == {"type": "any"}
    assert payload["tools"][0]["input_schema"] == {"type": "object", "properties": {}}
    assert [turn["role"] for turn in payload["messages"]] == [
        "user",
        "assistant",
        "user",
    ]
    assert payload["messages"][0]["content"][1]["source"]["media_type"] == "image/png"
    assert payload["messages"][1]["content"] == [
        {"type": "tool_use", "id": "call-1", "name": "lookup", "input": {"q": 1}}
    ]
    assert payload["messages"][2]["content"][0]["type"] == "tool_result"

###############################################################################
def test_messages_models_run_structured_output_through_the_messages_endpoint(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_post(self, url, **kwargs):  # noqa: ANN001, ANN003, ANN202
        captured["url"] = url
        captured["headers"] = kwargs["headers"]
        captured["json"] = kwargs["json"]
        return httpx.Response(
            200,
            json={
                "id": "msg_1",
                "stop_reason": "tool_use",
                "usage": {"input_tokens": 7, "output_tokens": 3},
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_1",
                        "name": "submit_structured_response",
                        "input": {"answer": "structured"},
                    }
                ],
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.Client, "post", fake_post)
    provider = OpenCodeProvider(api_key="test-key", provider_name=OPENCODE_GO_PROVIDER)

    result = provider.structured_output(
        LLMRequest(
            model="qwen3.8-max",
            provider_session_id="conversation-1",
            messages=[{"role": "user", "content": "Hello"}],
        ),
        schema=_StructuredPayload,
    )

    assert result == {"answer": "structured"}
    assert captured["url"] == "https://opencode.ai/zen/go/v1/messages"
    assert captured["headers"]["x-api-key"] == "test-key"
    assert captured["headers"]["x-opencode-session"] == "conversation-1"
    assert captured["json"]["tools"][0]["name"] == "submit_structured_response"
    assert result.context_usage["reported_input_tokens"] == 7

###############################################################################
def test_messages_error_keeps_status_and_provider_detail(monkeypatch) -> None:
    def fake_post(self, url, **kwargs):  # noqa: ANN001, ANN003, ANN202
        return httpx.Response(
            400,
            text="prompt is too long for this model",
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.Client, "post", fake_post)
    provider = OpenCodeProvider(api_key="test-key", provider_name=OPENCODE_GO_PROVIDER)

    with pytest.raises(LLMProviderRequestError) as error:
        provider.chat(
            LLMRequest(
                model="minimax-m3",
                provider_session_id="conversation-1",
                messages=[{"role": "user", "content": "Hello"}],
            )
        )

    assert error.value.code == "context_limit_exceeded"
