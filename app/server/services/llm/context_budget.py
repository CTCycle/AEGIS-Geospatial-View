from __future__ import annotations

import json
import math
import re
from dataclasses import replace
from typing import Any

from server.services.llm.cloud_catalog import get_model_context_profile
from server.services.llm.errors import LLMContextLimitError
from server.services.llm.types import ContextUsage, LLMRequest, ModelContextProfile
from server.prompts.context import build_compacted_history_summary

CONTEXT_HEADROOM_TOKENS = 512
UNKNOWN_OUTPUT_ALLOWANCE_TOKENS = 2048
# Kept as an import-compatible marker for older callers; known models now
# initialize to their full supported cap instead of this minimum.
MIN_OLLAMA_CONTEXT_WINDOW = 2048

###############################################################################
def _positive_int(value: object) -> int | None:
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None

###############################################################################
def estimate_message_tokens(messages: list[dict[str, Any]]) -> int:
    total = 0
    for message in messages:
        role = str(message.get("role") or "")
        content = str(message.get("content") or "")
        # Lightweight deterministic estimate: roughly four chars per token,
        # plus a small per-message role/formatting overhead.
        total += max(1, math.ceil((len(role) + len(content)) / 4)) + 4
        total += estimate_json_tokens(message.get("tool_calls"))
    return max(total, 1)

###############################################################################
def estimate_json_tokens(value: object) -> int:
    if value is None:
        return 0
    return max(1, math.ceil(len(json.dumps(value, default=str, separators=(",", ":"))) / 4))

###############################################################################
def resolve_model_context_limit(model: str) -> int | None:
    """Resolve only known/trusted limits; never invent an 8K fallback."""

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
    return None

###############################################################################
def _request_metadata(request: LLMRequest) -> dict[str, Any]:
    return request.metadata if isinstance(request.metadata, dict) else {}

###############################################################################
def _profile_for_request(provider: str, request: LLMRequest) -> ModelContextProfile | None:
    normalized_provider = provider.strip().lower()
    metadata = _request_metadata(request)
    static_profile = get_model_context_profile(normalized_provider, request.model)
    context_limit = _positive_int(
        metadata.get("context_window_tokens")
        or metadata.get("context_length")
        or metadata.get("context_window")
        or metadata.get("max_context_tokens")
    )
    maximum_output = _positive_int(
        metadata.get("maximum_output_tokens")
        or metadata.get("max_output_tokens")
        or metadata.get("max_completion_tokens")
    )
    if static_profile is not None:
        if context_limit is None:
            context_limit = static_profile.context_window_tokens
        if maximum_output is None:
            maximum_output = static_profile.maximum_output_tokens
        return replace(
            static_profile,
            context_window_tokens=context_limit,
            maximum_output_tokens=maximum_output,
            metadata_source=str(
                metadata.get("context_profile_source") or static_profile.metadata_source
            ),
        )
    if context_limit is None:
        context_limit = resolve_model_context_limit(request.model)
    if context_limit is None and maximum_output is None:
        return None
    return ModelContextProfile(
        provider=normalized_provider,
        model=request.model,
        context_window_tokens=context_limit,
        maximum_output_tokens=maximum_output,
        default_output_reserve=maximum_output or UNKNOWN_OUTPUT_ALLOWANCE_TOKENS,
        metadata_source=str(metadata.get("context_profile_source") or "provider_metadata"),
    )

###############################################################################
def resolve_model_context_profile(
    provider: str,
    model: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> ModelContextProfile | None:
    """Return the same model profile used by provider request budgeting.

    Agent context assembly and the provider boundary must agree about the
    selected model's cap.  Keeping this small public adapter here prevents
    callers from maintaining a second, more conservative profile calculation.
    """

    return _profile_for_request(
        provider,
        LLMRequest(model=model, messages=[], metadata=dict(metadata or {})),
    )

###############################################################################
def _expected_output_tokens(request: LLMRequest, profile: ModelContextProfile | None) -> int:
    metadata = _request_metadata(request)
    configured = _positive_int(
        metadata.get("max_tokens")
        or metadata.get("max_output_tokens")
        or metadata.get("max_completion_tokens")
    )
    if configured is not None:
        if profile is not None and profile.maximum_output_tokens is not None:
            return min(configured, profile.maximum_output_tokens)
        return configured
    if profile is not None:
        return profile.maximum_output_tokens or profile.default_output_reserve
    return UNKNOWN_OUTPUT_ALLOWANCE_TOKENS

###############################################################################
def _context_components(
    request: LLMRequest,
    profile: ModelContextProfile | None,
) -> tuple[int, int, int, int, int | None]:
    expected_output = _expected_output_tokens(request, profile)
    tool_tokens = estimate_json_tokens([tool.__dict__ for tool in request.tools or []])
    schema_tokens = estimate_json_tokens(request.response_json_schema)
    limit = profile.context_window_tokens if profile is not None else None
    usable = (
        max(0, limit - expected_output - tool_tokens - schema_tokens - CONTEXT_HEADROOM_TOKENS)
        if limit is not None
        else None
    )
    return expected_output, tool_tokens, schema_tokens, CONTEXT_HEADROOM_TOKENS, usable

###############################################################################
def compute_context_usage(request: LLMRequest, *, provider: str) -> ContextUsage:
    normalized = provider.strip().lower()
    profile = _profile_for_request(normalized, request)
    estimated = estimate_message_tokens(request.messages)
    expected_output, tool_tokens, schema_tokens, safety_margin, usable = _context_components(
        request, profile
    )
    limit = profile.context_window_tokens if profile is not None else None
    percent = (
        round((estimated / max(usable, 1)) * 100, 1)
        if usable is not None
        else None
    )
    return ContextUsage(
        estimated_input_tokens=estimated,
        selected_context_window=limit,
        model_context_limit=limit,
        usage_percent=percent,
        provider=normalized,
        model=request.model,
        reserved_output_tokens=expected_output,
        expected_output_tokens=expected_output,
        tool_schema_tokens=tool_tokens,
        response_schema_tokens=schema_tokens,
        safety_margin_tokens=safety_margin,
        usable_prompt_budget_tokens=usable,
        current_conversation_tokens=estimated,
        context_profile_source=profile.metadata_source if profile is not None else "unknown",
        compaction_applied=bool(_request_metadata(request).get("_context_compaction_applied")),
    )

###############################################################################
def compute_ollama_context_usage(
    request: LLMRequest,
    *,
    response_schema: object | None = None,
) -> ContextUsage:
    effective = (
        replace(request, response_json_schema=response_schema)
        if response_schema is not None
        else request
    )
    return compute_context_usage(effective, provider="ollama")

###############################################################################
def _message_blocks(messages: list[dict[str, Any]]) -> list[tuple[list[int], list[dict[str, Any]]]]:
    """Group tool-call/result pairs so compaction never leaves a broken pair."""

    blocks: list[tuple[list[int], list[dict[str, Any]]]] = []
    index = 0
    while index < len(messages):
        message = messages[index]
        role = str(message.get("role") or "")
        if role == "assistant" and message.get("tool_calls"):
            end = index + 1
            while end < len(messages) and str(messages[end].get("role") or "") == "tool":
                end += 1
            blocks.append((list(range(index, end)), messages[index:end]))
            index = end
            continue
        blocks.append(([index], [message]))
        index += 1
    return blocks

###############################################################################
def _compact_messages(messages: list[dict[str, Any]], budget: int) -> tuple[list[dict[str, Any]], bool]:
    if estimate_message_tokens(messages) <= budget:
        return list(messages), False

    blocks = _message_blocks(messages)
    last_user_index = next(
        (index for index in range(len(messages) - 1, -1, -1) if messages[index].get("role") == "user"),
        len(messages) - 1,
    )
    pinned_indices = {
        index
        for index, message in enumerate(messages)
        if str(message.get("role") or "") in {"system", "developer"}
    }
    pinned_indices.add(last_user_index)
    for indices, block in blocks:
        if any(message.get("role") == "tool" for message in block):
            pinned_indices.update(indices)

    selected_indices: set[int] = set(pinned_indices)
    dropped: list[dict[str, Any]] = []
    for indices, block in reversed(blocks):
        if set(indices) & selected_indices:
            continue
        candidate = [messages[index] for index in sorted(selected_indices | set(indices))]
        if estimate_message_tokens(candidate) <= budget:
            selected_indices.update(indices)
        else:
            dropped.extend(block)

    if dropped:
        # Reserve space for the bounded summary as well as the newest
        # messages.  The first pass may have filled the budget completely;
        # remove the oldest non-pinned blocks until the summary fits.
        summary_char_limit = 1800
        while True:
            snippets = []
            for message in reversed(dropped):
                content = str(message.get("content") or "").strip()
                if content:
                    snippet_limit = min(320, summary_char_limit)
                    snippets.append(f"{message.get('role', 'message')}: {content[:snippet_limit]}")
                if sum(len(item) for item in snippets) >= summary_char_limit:
                    break
            summary = {
                "role": "system",
                "content": build_compacted_history_summary(" | ".join(reversed(snippets))),
            }
            selected = [messages[index] for index in range(len(messages)) if index in selected_indices]
            system_count = sum(
                1 for message in selected if str(message.get("role") or "") in {"system", "developer"}
            )
            candidate = list(selected)
            candidate.insert(system_count, summary)
            if estimate_message_tokens(candidate) <= budget:
                break

            removable = next(
                (
                    (indices, block)
                    for indices, block in blocks
                    if all(index in selected_indices for index in indices)
                    and not any(index in pinned_indices for index in indices)
                ),
                None,
            )
            if removable is not None:
                indices, block = removable
                selected_indices.difference_update(indices)
                dropped.extend(block)
                continue

            if summary_char_limit > 120:
                summary_char_limit = max(120, summary_char_limit - 80)
                continue
            return [], True
        selected = candidate

    if estimate_message_tokens(selected) > budget:
        return [], True
    return selected, True

###############################################################################
def prepare_request(request: LLMRequest, *, provider: str) -> LLMRequest:
    profile = _profile_for_request(provider, request)
    if profile is None or profile.context_window_tokens is None:
        # Unknown provider limits must be attempted and diagnosed from the
        # provider response; do not apply a fabricated local ceiling.
        return request
    usage = compute_context_usage(request, provider=provider)
    usable = usage.usable_prompt_budget_tokens
    if usable is None or usage.estimated_input_tokens <= usable:
        return request
    messages, compacted = _compact_messages(request.messages, usable)
    if not messages:
        raise LLMContextLimitError(
            provider=provider,
            model=request.model,
            stage="context_preparation",
            detail=(
                "The system instructions, current turn, and required tool results exceed "
                f"the usable prompt budget of {usable:,} tokens for {request.model}."
            ),
        )
    metadata = dict(_request_metadata(request))
    metadata["_context_compaction_applied"] = compacted
    prepared = replace(request, messages=messages, metadata=metadata)
    prepared_usage = compute_context_usage(prepared, provider=provider)
    if prepared_usage.usable_prompt_budget_tokens is not None and (
        prepared_usage.estimated_input_tokens > prepared_usage.usable_prompt_budget_tokens
    ):
        raise LLMContextLimitError(
            provider=provider,
            model=request.model,
            stage="context_preparation",
            detail=(
                "The required conversation context still exceeds the usable prompt budget "
                f"of {prepared_usage.usable_prompt_budget_tokens:,} tokens for {request.model}."
            ),
        )
    return prepared
