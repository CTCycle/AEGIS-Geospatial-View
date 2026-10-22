from __future__ import annotations
from types import SimpleNamespace
import pytest
import json
from server.services.llm.errors import LLMProviderRequestError, LLMRequestSchemaError
from server.services.llm.openai_provider import OpenAIProvider
from server.services.llm.types import LLMRequest, LLMToolDefinition
from server.domain.agent.tool_result import ToolExecutionError, ToolExecutionMetadata, ToolResult
from server.services.llm.deepseek_provider import DeepSeekProvider
from server.services.llm.google_provider import GoogleProvider
from server.services.llm.ollama import OllamaProvider
from server.services.llm.opencode_provider import OPENCODE_GO_PROVIDER, OpenCodeProvider
from server.services.llm.response_serialization import dump_response_payload

# --- test_errors.py ---




###############################################################################
def test_provider_connection_errors_are_retryable() -> None:
    error = LLMProviderRequestError.from_exception(
        ConnectionError("socket unavailable"),
        provider="opencode-go",
        model="mimo-v2.5",
        stage="structured_output",
    )

    assert error.code == "provider_request_failed"
    assert error.retryable is True

###############################################################################
def test_provider_timeouts_are_terminal_and_preserve_context_usage() -> None:
    context_usage = {
        "estimated_input_tokens": 321,
        "selected_context_window": None,
        "model_context_limit": None,
        "usage_percent": None,
        "provider": "opencode-go",
        "model": "deepseek-v4-flash",
    }

    error = LLMProviderRequestError.from_exception(
        TimeoutError("request timed out"),
        provider="opencode-go",
        model="deepseek-v4-flash",
        stage="structured_output",
        context_usage=context_usage,
    )

    assert error.code == "provider_timeout"
    assert error.retryable is False
    assert error.context_usage == context_usage
    assert error.timeout_origin == "provider_transport"

###############################################################################
def test_bounded_deadline_timeout_is_classified_as_application_deadline() -> None:
    error = LLMProviderRequestError.from_exception(
        TimeoutError("The bounded LLM request deadline has expired."),
        provider="opencode-go",
        model="deepseek-v4-flash",
        stage="structured_output",
    )

    assert error.code == "provider_timeout"
    assert error.timeout_origin == "application_deadline"

###############################################################################
def test_timeout_origin_can_preserve_cancellation_classification() -> None:
    error = LLMProviderRequestError(
        provider="opencode-go",
        model="deepseek-v4-flash",
        stage="structured_output",
        code="provider_timeout",
        retryable=False,
        timeout_origin="cancelled",
    )

    assert error.timeout_origin == "cancelled"

###############################################################################
def test_gateway_timeout_is_terminal_and_not_retryable() -> None:

    ###############################################################################
    class _GatewayTimeout(Exception):
        response = SimpleNamespace(status_code=504)

    error = LLMProviderRequestError.from_exception(
        _GatewayTimeout("upstream gateway timeout"),
        provider="opencode-go",
        model="deepseek-v4-flash",
        stage="structured_output",
    )

    assert error.code == "provider_timeout"
    assert error.retryable is False

###############################################################################
def test_non_transient_provider_errors_are_not_retryable() -> None:
    error = LLMProviderRequestError.from_exception(
        ValueError("invalid request"),
        provider="opencode-go",
        model="mimo-v2.5",
        stage="structured_output",
    )

    assert error.retryable is False

###############################################################################
def test_provider_context_overflow_is_not_misclassified_as_capability_failure() -> None:

    ###############################################################################
    class _ProviderContextError(Exception):
        response = SimpleNamespace(status_code=413)

    error = LLMProviderRequestError.from_exception(
        _ProviderContextError("maximum context length exceeded"),
        provider="opencode-go",
        model="deepseek-v4-flash",
        stage="structured_output",
    )

    assert error.category == "context_limit"
    assert error.code == "context_limit_exceeded"

###############################################################################
def test_provider_bad_request_without_capability_evidence_stays_provider_api() -> None:

    ###############################################################################
    class _ProviderBadRequest(Exception):
        response = SimpleNamespace(status_code=400)

    error = LLMProviderRequestError.from_exception(
        _ProviderBadRequest("HTTP Error 400: Bad Request"),
        provider="ollama",
        model="qwen3.5:2b",
        stage="structured_output",
    )

    assert error.category == "provider_api"
    assert error.code == "provider_bad_request"

###############################################################################
def test_opencode_session_contract_rejection_is_sanitized() -> None:

    ###############################################################################
    class _OpenCodeContractError(Exception):
        response = SimpleNamespace(status_code=400)

    error = LLMProviderRequestError.from_exception(
        _OpenCodeContractError(
            "x-opencode-session is required; bearer=super-secret-token"
        ),
        provider="opencode-go",
        model="deepseek-v4-flash",
        stage="structured_output",
    )

    assert error.code == "provider_contract_rejected"
    assert error.retryable is False
    assert "super-secret-token" not in str(error)

###############################################################################
def test_explicit_provider_capability_rejection_is_classified_as_model_capability() -> (
    None
):

    ###############################################################################
    class _ProviderCapabilityError(Exception):
        response = SimpleNamespace(status_code=400)

    error = LLMProviderRequestError.from_exception(
        _ProviderCapabilityError("model does not support structured output"),
        provider="ollama",
        model="qwen3.5:2b",
        stage="structured_output",
    )

    assert error.category == "model_capability"
    assert error.code == "provider_model_incompatible"

###############################################################################
def test_malformed_tool_definition_is_classified_at_provider_boundary() -> None:
    request = LLMRequest(
        model="gpt-4.1",
        messages=[{"role": "user", "content": "hi"}],
        tools=[
            LLMToolDefinition(
                name="lookup",
                description="Lookup",
                parameters_json_schema={"type": "object", "properties": []},
            )
        ],
    )

    with pytest.raises(LLMRequestSchemaError) as error:
        OpenAIProvider(api_key="test")._validate_request_capabilities(request)
    assert error.value.category == "schema_definition"

# --- test_provider_contracts.py ---



###############################################################################
def _tool() -> LLMToolDefinition:
    return LLMToolDefinition(
        name="resolve_location",
        description="Resolve a place name.",
        parameters_json_schema={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    )

###############################################################################
def _request(provider: str, model: str) -> LLMRequest:
    return LLMRequest(
        provider=provider,
        model=model,
        messages=[{"role": "user", "content": "Find Zurich."}],
        tools=[_tool()],
    )

###############################################################################
class _Completions:

    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    # -------------------------------------------------------------------------
    def create(self, **kwargs):  # noqa: ANN003, ANN201
        self.calls.append(kwargs)
        message = SimpleNamespace(
            content="",
            tool_calls=[
                SimpleNamespace(
                    id="call-1",
                    function=SimpleNamespace(
                        name="resolve_location",
                        arguments=json.dumps({"query": "Zurich"}),
                    ),
                )
            ],
        )
        return SimpleNamespace(
            choices=[SimpleNamespace(message=message, finish_reason="tool_calls")],
            model_dump=lambda *, mode="json", warnings=False: {"choices": []},
        )

###############################################################################
class _OpenAICompatibleClient:

    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        self.completions = _Completions()
        self.chat = SimpleNamespace(completions=self.completions)

###############################################################################
def test_google_native_tool_contract_uses_function_declarations() -> None:
    contents = GoogleProvider._contents_from_messages(
        [
            {
                "role": "assistant",
                "tool_calls": [{"name": "resolve_location", "arguments": {}}],
            },
            {"role": "tool", "name": "resolve_location", "content": '{"ok":true}'},
        ]
    )
    schema = GoogleProvider.tool_to_google_schema(_tool())
    assert schema["parameters"]["required"] == ["query"]
    assert contents[0]["role"] == "model"
    assert contents[1]["parts"][0]["function_response"]["name"] == "resolve_location"

###############################################################################
def test_deepseek_and_opencode_chat_contracts_are_chat_completions_native(
    monkeypatch,
) -> None:
    for provider, model in (
        (
            DeepSeekProvider(api_key="test", base_url="https://deepseek.test"),
            "deepseek-v4-flash",
        ),
        (
            OpenCodeProvider(api_key="test", provider_name=OPENCODE_GO_PROVIDER),
            "deepseek-v4-flash",
        ),
    ):
        client = _OpenAICompatibleClient()
        monkeypatch.setattr(
            provider,
            "_client",
            lambda _request=None, *, stage="chat", client=client: client,
        )
        result = provider.chat(_request(provider.provider_name, model))
        call = client.completions.calls[0]
        assert call["tools"][0]["type"] == "function"
        assert call["tool_choice"] == "auto"
        assert result.tool_calls[0].arguments == {"query": "Zurich"}

###############################################################################
def test_ollama_chat_contract_emits_native_tools_and_parses_results() -> None:
    captured: dict[str, object] = {}

    ###############################################################################
    class _Provider(OllamaProvider):

        # -------------------------------------------------------------------------
        def supports_tools(self, model: str) -> bool:
            _ = model
            return True

        # -------------------------------------------------------------------------
        def _post_json(self, path: str, payload: dict[str, object]):
            captured["path"] = path
            captured["payload"] = payload
            return {
                "message": {
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "function": {
                                "name": "resolve_location",
                                "arguments": {"query": "Zurich"},
                            },
                        }
                    ],
                }
            }

    provider = _Provider(base_url="http://ollama.test")
    result = provider.chat(_request("ollama", "llama3.2"))
    assert captured["path"] == "/api/chat"
    assert captured["payload"]["tools"][0]["function"]["name"] == "resolve_location"
    assert result.tool_calls[0].arguments == {"query": "Zurich"}

###############################################################################
def test_provider_contract_error_remains_structured() -> None:
    result = ToolResult(
        call_id="call-1",
        tool_name="execute_geospatial_capability",
        status="failed",
        summary="upstream unavailable",
        error=ToolExecutionError(
            error_type="provider_unavailable",
            code="provider_unavailable",
            message="upstream unavailable",
            retryable=False,
            recovery="choose_alternate_tool",
        ),
        metadata=ToolExecutionMetadata(duration_ms=0),
    )
    assert result.error is not None
    assert result.error.code == "provider_unavailable"
    assert result.error.recovery == "choose_alternate_tool"

# --- test_llm_request_contract.py ---


###############################################################################
def test_llm_request_preserves_tools_and_schema_for_provider_validation() -> None:
    tool = LLMToolDefinition(
        name="lookup",
        description="Lookup",
        parameters_json_schema={"type": "object", "properties": {}},
    )

    request = LLMRequest(
        model="test-model",
        messages=[{"role": "user", "content": "hi"}],
        tools=[tool],
        response_json_schema={"type": "object", "properties": {}},
    )
    assert request.tools == [tool]
    assert request.response_json_schema == {"type": "object", "properties": {}}

# --- test_native_tool_parse_errors.py ---



###############################################################################
def test_openai_preserves_invalid_json_and_real_empty_object() -> None:
    calls = OpenAIProvider._parse_tool_calls(
        {
            "output": [
                {
                    "type": "function_call",
                    "call_id": "bad",
                    "name": "resolve",
                    "arguments": "{not-json",
                },
                {
                    "type": "function_call",
                    "call_id": "empty",
                    "name": "resolve",
                    "arguments": {},
                },
            ]
        }
    )

    assert calls[0].arguments is None
    assert calls[0].parse_error == "invalid_json"
    assert calls[1].arguments == {}
    assert calls[1].parse_error is None

###############################################################################
def test_google_and_ollama_reject_non_object_arguments() -> None:
    google_calls = GoogleProvider._parse_tool_calls(
        {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "functionCall": {
                                    "name": "resolve",
                                    "args": ["not", "an", "object"],
                                }
                            }
                        ]
                    }
                }
            ]
        }
    )
    ollama_calls = OllamaProvider._parse_tool_calls(
        {
            "tool_calls": [
                {
                    "id": "call-1",
                    "function": {"name": "resolve", "arguments": "[]"},
                }
            ]
        }
    )

    assert google_calls[0].arguments is None
    assert google_calls[0].parse_error == "arguments_not_object"
    assert ollama_calls[0].arguments is None
    assert ollama_calls[0].parse_error == "arguments_not_object"

###############################################################################
def test_deepseek_preserves_missing_name_as_a_parse_error() -> None:
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content="",
                    tool_calls=[
                        SimpleNamespace(
                            id="call-1",
                            function=SimpleNamespace(name="", arguments="{}"),
                        )
                    ],
                )
            )
        ]
    )

    _content, calls = DeepSeekProvider(api_key="test")._parse_choice(response)

    assert calls[0].name == ""
    assert calls[0].arguments == {}
    assert calls[0].parse_error == "missing_name"

# --- test_response_serialization.py ---



###############################################################################
def test_dump_response_payload_preserves_usage_from_sdk_like_objects() -> None:
    payload = dump_response_payload(
        SimpleNamespace(
            usage=SimpleNamespace(prompt_tokens=123, completion_tokens=9),
            response=SimpleNamespace(input_tokens=88),
        )
    )

    assert payload["usage"] == {"prompt_tokens": 123, "completion_tokens": 9}
    assert payload["response"] == {"input_tokens": 88}