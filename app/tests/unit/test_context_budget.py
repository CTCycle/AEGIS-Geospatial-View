from __future__ import annotations

import pytest

from server.prompts.context import build_compacted_history_summary
from server.services.llm.errors import LLMContextLimitError
from server.services.llm.context_budget import (
    RESPONSE_SCHEMA_EMBEDDED_METADATA_KEY,
    apply_reported_usage,
    calculate_context_usage_percent,
    compute_context_usage,
    compute_ollama_context_usage,
    estimate_message_tokens,
    prepare_request,
    resolve_model_context_limit,
    resolve_model_context_profile,
)
from server.services.llm.types import LLMRequest, LLMToolDefinition


###############################################################################
def _request(
    content: str,
    *,
    model: str = "unknown-local-model",
    metadata: dict[str, object] | None = None,
) -> LLMRequest:
    return LLMRequest(
        model=model,
        messages=[
            {"role": "system", "content": "You are concise."},
            {"role": "user", "content": content},
        ],
        metadata=dict(metadata or {}),
    )


###############################################################################
def test_static_catalog_profile_is_exact_and_provider_scoped() -> None:
    usage = compute_context_usage(
        _request(
            "hello",
            model="gpt-5-mini",
            metadata={"max_tokens": 1024},
        ),
        provider="openai",
    )

    assert usage.selected_context_window == 400_000
    assert usage.model_context_limit == 400_000
    assert usage.usable_prompt_budget_tokens == 398_464
    assert usage.context_profile_source == "openai_model_catalog"
    assert usage.provider == "openai"
    assert usage.peak_request_tokens == usage.estimated_input_tokens
    assert usage.total_input_tokens == usage.estimated_input_tokens


###############################################################################
def test_model_name_alone_never_creates_a_local_context_cap() -> None:
    assert resolve_model_context_limit("llama3.2") is None
    assert resolve_model_context_limit("custom-4k") is None
    assert resolve_model_context_profile("ollama", "qwen3.5:2b") is None

    usage = compute_ollama_context_usage(_request("hello", model="qwen3.5:2b"))
    assert usage.selected_context_window is None
    assert usage.usage_percent is None
    assert usage.usage_source == "estimated"
    assert usage.estimated_input_tokens > 0


###############################################################################
def test_provider_metadata_supplies_the_local_cap_and_schema_reservation() -> None:
    usage = compute_ollama_context_usage(
        _request(
            "x" * 5000,
            model="local-alias",
            metadata={
                "context_window_tokens": 40_960,
                "maximum_output_tokens": 4096,
                "context_profile_source": "ollama_show_model_info",
            },
        ),
        response_schema={
            "type": "object",
            "properties": {"answer": {"type": "string"}},
        },
    )

    assert usage.selected_context_window == 40_960
    assert usage.response_schema_tokens > 0
    assert usage.reserved_output_tokens == 4096
    assert usage.context_profile_source == "ollama_show_model_info"
    assert usage.usable_prompt_budget_tokens == 36_352


###############################################################################
def test_complete_request_counts_messages_tools_and_response_schema_before_compaction() -> (
    None
):
    tool = LLMToolDefinition(
        name="execute",
        description="Execute a geospatial operation.",
        parameters_json_schema={
            "type": "object",
            "properties": {"location": {"type": "string"}},
            "required": ["location"],
        },
    )
    request = LLMRequest(
        model="bounded-model",
        messages=[{"role": "user", "content": "Find the target."}],
        tools=[tool],
        response_json_schema={
            "type": "object",
            "properties": {"answer": {"type": "string"}},
        },
        metadata={
            "context_window_tokens": 2048,
            "maximum_output_tokens": 256,
            "context_profile_source": "provider_metadata",
        },
    )

    usage = compute_context_usage(request, provider="test")

    assert usage.tool_schema_tokens > 0
    assert usage.response_schema_tokens > 0
    assert usage.estimated_input_tokens > usage.current_conversation_tokens
    assert usage.usable_prompt_budget_tokens == 1280
    assert usage.usage_percent is not None


###############################################################################
def test_embedded_response_schema_is_counted_once_as_a_message() -> None:
    messages = [
        {"role": "system", "content": "Extract the requested object."},
        {
            "role": "system",
            "content": '{"type":"object","properties":{"answer":{"type":"string"}}}',
        },
        {"role": "user", "content": "Hello"},
    ]
    request = LLMRequest(
        model="deepseek-v4-flash",
        messages=messages,
        response_json_schema={
            "type": "object",
            "properties": {"answer": {"type": "string"}},
        },
        metadata={RESPONSE_SCHEMA_EMBEDDED_METADATA_KEY: True},
    )

    usage = compute_context_usage(request, provider="opencode-go")

    assert usage.response_schema_tokens == 0
    assert usage.estimated_input_tokens == estimate_message_tokens(messages)


###############################################################################
def test_provider_reported_input_and_output_replace_estimate_without_losing_it() -> (
    None
):
    usage = compute_context_usage(
        _request(
            "hello",
            model="reported-model",
            metadata={
                "context_window_tokens": 4096,
                "maximum_output_tokens": 512,
                "context_profile_source": "provider_metadata",
            },
        ),
        provider="test",
    )

    updated = apply_reported_usage(
        usage,
        {"usage": {"prompt_tokens": 700, "completion_tokens": 42}},
    )

    assert updated.estimated_input_tokens != 700
    assert updated.reported_input_tokens == 700
    assert updated.reported_output_tokens == 42
    assert updated.effective_input_tokens == 700
    assert updated.peak_request_tokens == 700
    assert updated.total_input_tokens == 700
    assert updated.total_output_tokens == 42
    assert updated.usage_source == "provider_reported"
    assert updated.usage_percent == round(700 / 4096 * 100, 1)


###############################################################################
def test_output_only_provider_usage_is_hybrid() -> None:
    usage = compute_context_usage(_request("hello"), provider="test")
    updated = apply_reported_usage(usage, {"eval_count": 19})

    assert updated.reported_input_tokens is None
    assert updated.reported_output_tokens == 19
    assert updated.usage_source == "hybrid"
    assert updated.estimated_input_tokens == updated.effective_input_tokens
    assert updated.total_output_tokens == 19


###############################################################################
def test_nested_provider_usage_is_preserved_from_stream_completion_payload() -> None:
    usage = compute_context_usage(
        _request(
            "hello",
            model="nested-usage-model",
            metadata={
                "context_window_tokens": 4096,
                "maximum_output_tokens": 512,
                "context_profile_source": "provider_metadata",
            },
        ),
        provider="test",
    )

    updated = apply_reported_usage(
        usage,
        {"response": {"usage": {"input_tokens": 700, "output_tokens": 42}}},
    )

    assert updated.reported_input_tokens == 700
    assert updated.reported_output_tokens == 42
    assert updated.usage_source == "provider_reported"
    assert updated.usage_percent == round(700 / 4096 * 100, 1)


def test_context_usage_percent_uses_model_limit_and_can_show_overage() -> None:
    assert calculate_context_usage_percent(700, 4096) == round(700 / 4096 * 100, 1)
    assert calculate_context_usage_percent(5000, 4096) == round(5000 / 4096 * 100, 1)
    assert calculate_context_usage_percent(700, None) is None


###############################################################################
def test_prepare_request_compacts_explicitly_bounded_history_and_preserves_current_input() -> (
    None
):
    request = LLMRequest(
        model="custom-alias",
        messages=[
            {"role": "system", "content": "system"},
            *[{"role": "user", "content": "x" * 2000} for _ in range(20)],
            {"role": "user", "content": "CURRENT"},
        ],
        metadata={
            "context_window_tokens": 4096,
            "maximum_output_tokens": 512,
            "context_profile_source": "provider_metadata",
        },
    )
    prepared = prepare_request(request, provider="test")

    assert len(prepared.messages) < len(request.messages)
    assert prepared.messages[-1]["content"] == "CURRENT"
    assert any(
        str(item.get("content")).startswith(build_compacted_history_summary(""))
        for item in prepared.messages
    )
    assert prepared.metadata["_context_compaction_applied"] is True


###############################################################################
def test_prepare_request_does_not_invent_limit_for_unknown_model() -> None:
    request = LLMRequest(
        model="unknown-small",
        messages=[
            {"role": "system", "content": "system"},
            *[{"role": "user", "content": "x" * 2000} for _ in range(20)],
            {"role": "user", "content": "CURRENT"},
        ],
    )

    prepared = prepare_request(request, provider="test")

    assert prepared.messages == request.messages


def test_unknown_model_rejects_oversized_current_request_without_inventing_capacity() -> (
    None
):
    request = _request("x" * 200_000)
    with pytest.raises(LLMContextLimitError):
        prepare_request(request, provider="unknown")
    usage = compute_context_usage(request, provider="unknown")
    assert usage.model_context_limit is None
    assert usage.usage_percent is None


def test_unknown_model_compacts_history_to_application_input_ceiling() -> None:
    request = LLMRequest(
        model="unknown",
        messages=[
            {"role": "system", "content": "Stable instructions"},
            *[{"role": "user", "content": "old" * 4000} for _ in range(50)],
            {"role": "user", "content": "Show Rome"},
        ],
    )
    prepared = prepare_request(request, provider="unknown")
    assert (
        compute_context_usage(prepared, provider="unknown").estimated_input_tokens
        <= 32_768
    )
    assert prepared.messages[-1]["content"] == "Show Rome"
    assert prepared.metadata["_context_compaction_applied"] is True


###############################################################################
def test_context_limit_failure_preserves_preflight_usage() -> None:
    request = _request(
        "x" * 100_000,
        model="bounded-model",
        metadata={
            "context_window_tokens": 1024,
            "maximum_output_tokens": 256,
            "context_profile_source": "provider_metadata",
        },
    )

    with pytest.raises(LLMContextLimitError) as error:
        prepare_request(request, provider="test")

    assert error.value.context_usage is not None
    assert error.value.context_usage["estimated_input_tokens"] > 0
    assert error.value.context_usage["usable_prompt_budget_tokens"] == 256
