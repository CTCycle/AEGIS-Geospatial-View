from __future__ import annotations

from server.services.llm.context_budget import (
    compute_context_usage,
    compute_ollama_context_usage,
    resolve_model_context_limit,
    resolve_model_context_profile,
    prepare_request,
)
from server.prompts.context import build_compacted_history_summary
from server.services.llm.types import LLMRequest

###############################################################################
def _request(content: str, model: str = "llama3.2") -> LLMRequest:
    return LLMRequest(
        model=model,
        messages=[
            {"role": "system", "content": "You are concise."},
            {"role": "user", "content": content},
        ],
    )

###############################################################################
def test_known_model_context_initializes_to_full_supported_cap() -> None:
    usage = compute_ollama_context_usage(_request("hello"))

    assert usage.selected_context_window == resolve_model_context_limit("llama3.2")
    assert usage.model_context_limit == resolve_model_context_limit("llama3.2")
    assert usage.usable_prompt_budget_tokens is not None
    assert usage.usable_prompt_budget_tokens < usage.model_context_limit
    assert usage.context_profile_source != "unknown"
    assert usage.provider == "ollama"

###############################################################################
def test_ollama_context_reserves_schema_and_structured_output_capacity() -> None:
    usage = compute_ollama_context_usage(
        _request("x" * 5000, model="qwen3.5:2b"),
        response_schema={"type": "object", "properties": {"answer": {"type": "string"}}},
    )

    assert usage.selected_context_window == resolve_model_context_limit("qwen3.5:2b")
    assert usage.response_schema_tokens > 0
    assert usage.reserved_output_tokens > 0

###############################################################################
def test_ollama_context_clamps_to_model_limit_for_large_prompt() -> None:
    usage = compute_ollama_context_usage(_request("x" * 50000, model="custom-4k"))

    assert usage.selected_context_window == 4096
    assert usage.model_context_limit == 4096

###############################################################################
def test_unknown_model_limit_remains_explicitly_unknown() -> None:
    assert resolve_model_context_limit("unknown-local-model") is None
    assert resolve_model_context_profile("ollama", "unknown-local-model") is None

###############################################################################
def test_cloud_context_usage_does_not_select_local_window() -> None:
    usage = compute_context_usage(_request("hello", model="gpt-test"), provider="openai")

    assert usage.selected_context_window is None
    assert usage.provider == "openai"
    assert usage.estimated_input_tokens > 0

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

###############################################################################
def test_prepare_request_compacts_known_history_and_preserves_current_input() -> None:
    request = LLMRequest(
        model="custom-4k",
        messages=[
            {"role": "system", "content": "system"},
            *[{"role": "user", "content": "x" * 2000} for _ in range(20)],
            {"role": "user", "content": "CURRENT"},
        ],
        metadata={"maximum_output_tokens": 512},
    )
    prepared = prepare_request(request, provider="test")
    assert len(prepared.messages) < len(request.messages)
    assert prepared.messages[-1]["content"] == "CURRENT"
    assert any(
        str(item.get("content")).startswith(build_compacted_history_summary(""))
        for item in prepared.messages
    )
