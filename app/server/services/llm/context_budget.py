from __future__ import annotations

import math
import re

from server.services.llm.types import ContextUsage, LLMRequest

DEFAULT_MODEL_CONTEXT_LIMIT = 8192
MIN_OLLAMA_CONTEXT_WINDOW = 2048
CONTEXT_HEADROOM_TOKENS = 512
CONTEXT_WINDOW_STEP = 512


###############################################################################
def estimate_message_tokens(messages: list[dict[str, str]]) -> int:
    total = 0
    for message in messages:
        role = str(message.get("role") or "")
        content = str(message.get("content") or "")
        # Lightweight deterministic estimate: roughly four chars per token,
        # plus a small per-message role/formatting overhead.
        total += max(1, math.ceil((len(role) + len(content)) / 4)) + 4
    return max(total, 1)


###############################################################################
def resolve_model_context_limit(model: str) -> int:
    normalized = model.strip().lower()
    explicit = re.search(r"(?P<size>\d+)\s*k(?:$|[-_:])", normalized)
    if explicit:
        return max(1024, int(explicit.group("size")) * 1024)

    known_limits = {
        "llama3.2": 131072,
        "llama3.1": 131072,
        "qwen2.5": 32768,
        "qwen3": 40960,
        "mistral": 32768,
        "mixtral": 32768,
        "deepseek-r1": 131072,
        "gemma3": 131072,
        "nomic-embed-text": 8192,
    }
    for marker, limit in known_limits.items():
        if marker in normalized:
            return limit
    return DEFAULT_MODEL_CONTEXT_LIMIT


###############################################################################
def compute_ollama_context_usage(request: LLMRequest) -> ContextUsage:
    estimated = estimate_message_tokens(request.messages)
    model_limit = resolve_model_context_limit(request.model)
    needed = estimated + CONTEXT_HEADROOM_TOKENS
    stepped = math.ceil(needed / CONTEXT_WINDOW_STEP) * CONTEXT_WINDOW_STEP
    selected = max(MIN_OLLAMA_CONTEXT_WINDOW, min(model_limit, stepped))
    percent = round((estimated / max(selected, 1)) * 100, 1)
    return ContextUsage(
        estimated_input_tokens=estimated,
        selected_context_window=selected,
        model_context_limit=model_limit,
        usage_percent=percent,
        provider="ollama",
        model=request.model,
    )


###############################################################################
def compute_context_usage(request: LLMRequest, *, provider: str) -> ContextUsage:
    estimated = estimate_message_tokens(request.messages)
    normalized = provider.strip().lower()
    if normalized == "ollama":
        return compute_ollama_context_usage(request)
    model_limit = resolve_model_context_limit(request.model)
    percent = round((estimated / max(model_limit, 1)) * 100, 1)
    return ContextUsage(
        estimated_input_tokens=estimated,
        selected_context_window=None,
        model_context_limit=model_limit,
        usage_percent=percent,
        provider=normalized,
        model=request.model,
    )
