from types import SimpleNamespace

import pytest

from server.services.llm.errors import LLMProviderRequestError, LLMRequestSchemaError
from server.services.llm.openai_provider import OpenAIProvider
from server.services.llm.types import LLMRequest, LLMToolDefinition


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
