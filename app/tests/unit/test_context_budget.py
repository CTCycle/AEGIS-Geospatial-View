from __future__ import annotations

from server.services.llm.context_budget import (
    MIN_OLLAMA_CONTEXT_WINDOW,
    compute_context_usage,
    compute_ollama_context_usage,
    resolve_model_context_limit,
)
from server.services.llm.types import LLMRequest


def _request(content: str, model: str = "llama3.2") -> LLMRequest:
    return LLMRequest(
        model=model,
        messages=[
            {"role": "system", "content": "You are concise."},
            {"role": "user", "content": content},
        ],
    )


def test_ollama_context_uses_minimum_for_small_prompt() -> None:
    usage = compute_ollama_context_usage(_request("hello"))

    assert usage.selected_context_window == MIN_OLLAMA_CONTEXT_WINDOW
    assert usage.model_context_limit == resolve_model_context_limit("llama3.2")
    assert usage.provider == "ollama"


def test_ollama_context_clamps_to_model_limit_for_large_prompt() -> None:
    usage = compute_ollama_context_usage(_request("x" * 50000, model="custom-4k"))

    assert usage.selected_context_window == 4096
    assert usage.model_context_limit == 4096


def test_unknown_model_uses_fallback_limit() -> None:
    assert resolve_model_context_limit("unknown-local-model") == 8192


def test_cloud_context_usage_does_not_select_local_window() -> None:
    usage = compute_context_usage(_request("hello", model="gpt-test"), provider="openai")

    assert usage.selected_context_window is None
    assert usage.provider == "openai"
    assert usage.estimated_input_tokens > 0
