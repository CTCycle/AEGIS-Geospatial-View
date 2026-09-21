from __future__ import annotations

import json
import logging
import math
import re
from dataclasses import replace
from typing import Any

from server.common.typing import json_object
from server.services.llm.cloud_catalog import get_model_context_profile
from server.services.llm.errors import LLMContextLimitError
from server.services.llm.types import (
    ContextMetadataAuthority,
    ContextUsage,
    LLMRequest,
    ModelContextProfile,
)
from server.prompts.context import build_compacted_history_summary

CONTEXT_HEADROOM_TOKENS = 512
# Application resource policy, not a claim about an unknown model's capacity.
UNKNOWN_MODEL_INPUT_CEILING = 32_768
KNOWN_APPLICATION_INPUT_CEILING = 64_000
RESPONSE_SCHEMA_EMBEDDED_METADATA_KEY = "_response_schema_embedded_in_messages"
_LOGGER = logging.getLogger(__name__)
_CONTEXT_WINDOW_ALIASES = (
    "context_window_tokens",
    "context_length",
    "context_window",
    "max_context_tokens",
)
_MAXIMUM_OUTPUT_ALIASES = (
    "maximum_output_tokens",
    "max_output_tokens",
    "max_completion_tokens",
)
_AUTHORITY_RANK: dict[ContextMetadataAuthority, int] = {
    "unknown": 0,
    "inferred": 1,
    "configured": 2,
    "provider": 3,
}

###############################################################################
def _positive_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str) and re.fullmatch(r"\+?[0-9]+", value.strip()):
        number = int(value.strip())
        return number if number > 0 else None
    return None


###############################################################################
def _normalized_alias_value(
    metadata: dict[str, Any], aliases: tuple[str, ...], *, field_name: str
) -> int | None:
    present = [
        (key, _positive_int(metadata[key]))
        for key in aliases
        if key in metadata and metadata[key] is not None
    ]
    if not present:
        return None
    invalid = [key for key, value in present if value is None]
    if invalid:
        _LOGGER.warning(
            "Ignoring malformed %s metadata aliases: %s", field_name, invalid
        )
        return None
    values = {value for _, value in present if value is not None}
    if len(values) > 1:
        _LOGGER.warning(
            "Ignoring conflicting %s metadata aliases: %s",
            field_name,
            {key: value for key, value in present},
        )
        return None
    return next(iter(values))


###############################################################################
def normalize_model_context_profile(
    provider: str,
    model: str,
    *,
    metadata: dict[str, Any] | None = None,
    default_metadata_source: str = "provider_metadata",
    default_metadata_authority: ContextMetadataAuthority = "unknown",
) -> ModelContextProfile | None:
    """Normalize provider-extracted context metadata into one profile.

    Provider adapters own extraction of their raw payloads.  This function is
    intentionally strict about the canonical token fields so an invalid or
    conflicting provider response cannot become a guessed context limit.
    """

    payload = dict(metadata or {})
    context_window = _normalized_alias_value(
        payload, _CONTEXT_WINDOW_ALIASES, field_name="context window"
    )
    maximum_output = _normalized_alias_value(
        payload, _MAXIMUM_OUTPUT_ALIASES, field_name="maximum output"
    )
    default_output_reserve = _positive_int(payload.get("default_output_reserve"))
    if (
        context_window is None
        and maximum_output is None
        and default_output_reserve is None
    ):
        return None

    raw_authority = payload.get(
        "context_metadata_authority",
        payload.get("metadata_authority", default_metadata_authority),
    )
    authority = (
        raw_authority
        if raw_authority in _AUTHORITY_RANK
        else default_metadata_authority
        if default_metadata_authority in _AUTHORITY_RANK
        else "unknown"
    )
    if raw_authority not in _AUTHORITY_RANK:
        _LOGGER.warning("Ignoring unsupported context metadata authority: %r", raw_authority)
    source = payload.get("context_profile_source") or default_metadata_source
    return ModelContextProfile(
        provider=provider,
        model=model,
        context_window_tokens=context_window,
        maximum_output_tokens=maximum_output,
        default_output_reserve=default_output_reserve or maximum_output or 0,
        tokenizer_strategy=str(payload.get("tokenizer_strategy") or "chars_per_token_4"),
        supports_context_caching=bool(payload.get("supports_context_caching")),
        supports_server_compaction=bool(payload.get("supports_server_compaction")),
        metadata_source=str(source),
        metadata_authority=authority,
    )


###############################################################################
def profile_to_request_metadata(profile: ModelContextProfile) -> dict[str, Any]:
    """Return the canonical metadata snapshot used by request budgeting."""

    return {
        "context_window_tokens": profile.context_window_tokens,
        "maximum_output_tokens": profile.maximum_output_tokens,
        "default_output_reserve": profile.default_output_reserve,
        "tokenizer_strategy": profile.tokenizer_strategy,
        "supports_context_caching": profile.supports_context_caching,
        "supports_server_compaction": profile.supports_server_compaction,
        "context_profile_source": profile.metadata_source,
        "context_metadata_authority": profile.metadata_authority,
        "context_profile_provider": profile.provider,
        "context_profile_model": profile.model,
    }

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
    return max(
        1, math.ceil(len(json.dumps(value, default=str, separators=(",", ":"))) / 4)
    )

###############################################################################
def calculate_context_usage_percent(
    effective_input: int | None,
    model_context_limit: int | None,
) -> float | None:
    """Calculate usage against the model's exact context limit.

    ``usable_prompt_budget`` includes output and safety reservations and is
    intentionally reserved for request preparation.  The user-facing usage
    indicator describes how much of the model context window the request
    consumes, so it must use the model limit itself.
    """

    if effective_input is None or model_context_limit is None:
        return None
    if effective_input < 0 or model_context_limit <= 0:
        return None
    return round((effective_input / model_context_limit) * 100, 1)

###############################################################################
def _request_metadata(request: LLMRequest) -> dict[str, Any]:
    return request.metadata

###############################################################################
def _profile_for_request(
    provider: str, request: LLMRequest
) -> ModelContextProfile | None:
    normalized_provider = provider
    metadata = _request_metadata(request)
    static_profile = get_model_context_profile(normalized_provider, request.model)
    if static_profile is not None:
        normalized = normalize_model_context_profile(
            normalized_provider,
            request.model,
            metadata=metadata,
            default_metadata_source=static_profile.metadata_source,
            default_metadata_authority=static_profile.metadata_authority,
        )
        if normalized is None:
            return static_profile
        return replace(
            static_profile,
            context_window_tokens=(
                normalized.context_window_tokens
                if normalized.context_window_tokens is not None
                else static_profile.context_window_tokens
            ),
            maximum_output_tokens=(
                normalized.maximum_output_tokens
                if normalized.maximum_output_tokens is not None
                else static_profile.maximum_output_tokens
            ),
            default_output_reserve=(
                normalized.default_output_reserve
                or static_profile.default_output_reserve
            ),
            tokenizer_strategy=normalized.tokenizer_strategy,
            supports_context_caching=(
                normalized.supports_context_caching
                or static_profile.supports_context_caching
            ),
            supports_server_compaction=(
                normalized.supports_server_compaction
                or static_profile.supports_server_compaction
            ),
            metadata_source=normalized.metadata_source,
            metadata_authority=normalized.metadata_authority,
        )
    return normalize_model_context_profile(
        normalized_provider,
        request.model,
        metadata=metadata,
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
def _expected_output_tokens(
    request: LLMRequest, profile: ModelContextProfile | None
) -> int:
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
    # An unknown model has no trustworthy default output reservation.  A
    # caller that needs one must provide the actual request reservation in
    # metadata; inventing a cap here would make both compaction and the UI
    # falsely determinate.
    return 0

###############################################################################
def _context_components(
    request: LLMRequest,
    profile: ModelContextProfile | None,
) -> tuple[int, int, int, int, int | None]:
    metadata = _request_metadata(request)
    expected_output = _expected_output_tokens(request, profile)
    tool_tokens = (
        estimate_json_tokens([tool.__dict__ for tool in request.tools])
        if request.tools
        else 0
    )
    schema_tokens = (
        0
        if request.metadata.get(RESPONSE_SCHEMA_EMBEDDED_METADATA_KEY) is True
        else estimate_json_tokens(request.response_json_schema)
    )
    model_limit = profile.context_window_tokens if profile is not None else None
    declared_application_cap = _positive_int(
        metadata.get("application_input_token_ceiling")
    )
    application_cap = min(
        declared_application_cap
        or (
            KNOWN_APPLICATION_INPUT_CEILING
            if profile is not None
            else UNKNOWN_MODEL_INPUT_CEILING
        ),
        KNOWN_APPLICATION_INPUT_CEILING,
    )
    # The application ceiling limits input working-set size; it is not a
    # second model context window.  A very large requested output (for
    # example a provider maximum of 128K) must therefore not consume the
    # entire 64K application input budget.  Reserve output against the
    # declared model window, while only subtracting it from the application
    # ceiling when it is smaller than that ceiling.
    application_usable = (
        application_cap - expected_output - CONTEXT_HEADROOM_TOKENS
        if expected_output < application_cap
        else application_cap - CONTEXT_HEADROOM_TOKENS
    )
    model_usable = (
        model_limit - expected_output - CONTEXT_HEADROOM_TOKENS
        if model_limit is not None
        else application_usable
    )
    usable = max(0, min(application_usable, model_usable))
    return expected_output, tool_tokens, schema_tokens, CONTEXT_HEADROOM_TOKENS, usable

###############################################################################
def compute_context_usage(request: LLMRequest, *, provider: str) -> ContextUsage:
    normalized = provider
    profile = _profile_for_request(normalized, request)
    message_tokens = estimate_message_tokens(request.messages)
    expected_output, tool_tokens, schema_tokens, safety_margin, usable = (
        _context_components(request, profile)
    )
    estimated = message_tokens + tool_tokens + schema_tokens
    limit = profile.context_window_tokens if profile is not None else None
    percent = calculate_context_usage_percent(estimated, limit)
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
        current_conversation_tokens=message_tokens,
        context_profile_source=profile.metadata_source
        if profile is not None
        else "unknown",
        context_metadata_authority=profile.metadata_authority
        if profile is not None
        else "unknown",
        compaction_applied=bool(
            _request_metadata(request).get("_context_compaction_applied")
        ),
        peak_request_tokens=estimated,
        total_input_tokens=estimated,
    )

###############################################################################
def merge_provider_context_usage(
    usage: ContextUsage,
    provider_usage: dict[str, Any] | None,
) -> ContextUsage:
    """Merge provider telemetry without discarding the canonical profile.

    Providers commonly return token counts without repeating model metadata.
    Those counts are useful, but a partial payload must not turn a known
    context window into ``null``.  A reported limit is accepted only when it
    carries an authority stronger than the canonical request profile.
    """

    payload = provider_usage if isinstance(provider_usage, dict) else {}

    def non_negative_int(value: object) -> int | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, int) and value >= 0:
            return value
        if isinstance(value, str) and re.fullmatch(r"\+?[0-9]+", value.strip()):
            parsed = int(value.strip())
            return parsed if parsed >= 0 else None
        return None

    reported_input = non_negative_int(payload.get("reported_input_tokens"))
    reported_output = non_negative_int(payload.get("reported_output_tokens"))
    reported_limit = _positive_int(
        payload.get("model_context_limit")
        if payload.get("model_context_limit") is not None
        else payload.get("selected_context_window")
    )
    raw_authority = payload.get("context_metadata_authority")
    reported_authority: ContextMetadataAuthority = (
        raw_authority if raw_authority in _AUTHORITY_RANK else "unknown"
    )
    can_replace_limit = (
        reported_limit is not None
        and reported_authority != "unknown"
        and (
            usage.model_context_limit is None
            or _AUTHORITY_RANK[reported_authority]
            > _AUTHORITY_RANK[usage.context_metadata_authority]
        )
    )

    next_limit = reported_limit if can_replace_limit else usage.model_context_limit
    next_percent = calculate_context_usage_percent(
        reported_input
        if reported_input is not None
        else usage.effective_input_tokens,
        next_limit,
    )
    if reported_input is None and reported_output is None and not can_replace_limit:
        return usage

    if reported_input is not None:
        source = "provider_reported"
    elif reported_output is not None:
        source = "hybrid"
    else:
        source = usage.usage_source
    return replace(
        usage,
        reported_input_tokens=(
            reported_input
            if reported_input is not None
            else usage.reported_input_tokens
        ),
        reported_output_tokens=(
            reported_output
            if reported_output is not None
            else usage.reported_output_tokens
        ),
        selected_context_window=next_limit if can_replace_limit else usage.selected_context_window,
        model_context_limit=next_limit,
        usage_percent=next_percent,
        usage_source=source,
        context_profile_source=(
            str(payload.get("context_profile_source"))
            if can_replace_limit and isinstance(payload.get("context_profile_source"), str)
            else usage.context_profile_source
        ),
        context_metadata_authority=(
            reported_authority
            if can_replace_limit
            else usage.context_metadata_authority
        ),
        peak_request_tokens=(
            reported_input
            if reported_input is not None
            else usage.peak_request_tokens
        ),
        total_input_tokens=(
            reported_input
            if reported_input is not None
            else usage.total_input_tokens
        ),
        total_output_tokens=(
            reported_output
            if reported_output is not None
            else usage.total_output_tokens
        ),
    )

###############################################################################
def apply_reported_usage(
    usage: ContextUsage,
    raw_response: dict[str, Any] | None,
) -> ContextUsage:
    """Overlay provider-reported token counts without losing the estimate."""

    payload = raw_response if isinstance(raw_response, dict) else {}
    usage_payload = json_object(payload.get("usage"))
    nested_response = json_object(payload.get("response"))
    if not usage_payload:
        usage_payload = json_object(nested_response.get("usage"))
    usage_metadata = json_object(payload.get("usage_metadata"))
    if not usage_metadata:
        usage_metadata = json_object(nested_response.get("usage_metadata"))

    def first_non_negative(*values: object) -> int | None:
        for value in values:
            try:
                parsed = int(value)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                continue
            if parsed >= 0:
                return parsed
        return None

    input_tokens = first_non_negative(
        usage_payload.get("prompt_tokens"),
        usage_payload.get("input_tokens"),
        usage_metadata.get("prompt_token_count"),
        payload.get("prompt_eval_count"),
        payload.get("input_tokens"),
        nested_response.get("prompt_eval_count"),
        nested_response.get("input_tokens"),
    )
    output_tokens = first_non_negative(
        usage_payload.get("completion_tokens"),
        usage_payload.get("output_tokens"),
        usage_metadata.get("candidates_token_count"),
        payload.get("eval_count"),
        payload.get("output_tokens"),
        nested_response.get("eval_count"),
        nested_response.get("output_tokens"),
    )
    if input_tokens is None and output_tokens is None:
        return usage

    source = "provider_reported" if input_tokens is not None else "hybrid"
    effective_input = (
        input_tokens if input_tokens is not None else usage.estimated_input_tokens
    )
    percent = calculate_context_usage_percent(
        effective_input,
        usage.model_context_limit,
    )
    return replace(
        usage,
        reported_input_tokens=input_tokens,
        reported_output_tokens=output_tokens,
        peak_request_tokens=(
            input_tokens if input_tokens is not None else usage.peak_request_tokens
        ),
        total_input_tokens=(
            input_tokens if input_tokens is not None else usage.total_input_tokens
        ),
        total_output_tokens=(
            output_tokens if output_tokens is not None else usage.total_output_tokens
        ),
        usage_percent=percent,
        usage_source=source,
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
def _message_blocks(
    messages: list[dict[str, Any]],
) -> list[tuple[list[int], list[dict[str, Any]]]]:
    """Group tool-call/result pairs so compaction never leaves a broken pair."""

    blocks: list[tuple[list[int], list[dict[str, Any]]]] = []
    index = 0
    while index < len(messages):
        message = messages[index]
        role = str(message.get("role") or "")
        if role == "assistant" and message.get("tool_calls"):
            end = index + 1
            while (
                end < len(messages) and str(messages[end].get("role") or "") == "tool"
            ):
                end += 1
            blocks.append((list(range(index, end)), messages[index:end]))
            index = end
            continue
        if str(message.get("type") or "") in {
            "message",
            "reasoning",
            "function_call",
            "function_call_output",
        }:
            end = index + 1
            while end < len(messages) and str(messages[end].get("type") or "") in {
                "message",
                "reasoning",
                "function_call",
                "function_call_output",
            }:
                end += 1
            blocks.append((list(range(index, end)), messages[index:end]))
            index = end
            continue
        blocks.append(([index], [message]))
        index += 1
    return blocks

###############################################################################
def _compact_messages(
    messages: list[dict[str, Any]], budget: int
) -> tuple[list[dict[str, Any]], bool]:
    if estimate_message_tokens(messages) <= budget:
        return list(messages), False

    blocks = _message_blocks(messages)
    last_user_index = next(
        (
            index
            for index in range(len(messages) - 1, -1, -1)
            if messages[index].get("role") == "user"
        ),
        len(messages) - 1,
    )
    pinned_indices = {
        index
        for index, message in enumerate(messages)
        if str(message.get("role") or "") in {"system", "developer"}
    }
    pinned_indices.add(last_user_index)
    protocol_blocks = [
        (indices, block)
        for indices, block in blocks
        if any(
            message.get("role") == "tool"
            or str(message.get("type") or "")
            in {"reasoning", "function_call", "function_call_output"}
            for message in block
        )
    ]
    # Only the newest provider protocol block is pinned.  Older observations
    # have already been incorporated into canonical native state and may be
    # summarized without retaining an ever-growing chain of tool pairs.
    if protocol_blocks:
        pinned_indices.update(protocol_blocks[-1][0])

    selected_indices: set[int] = set(pinned_indices)
    dropped: list[dict[str, Any]] = []
    selected = list(messages)
    for indices, block in reversed(blocks):
        if set(indices) & selected_indices:
            continue
        candidate = [
            messages[index] for index in sorted(selected_indices | set(indices))
        ]
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
            snippets: list[str] = []
            for message in reversed(dropped):
                content = str(message.get("content") or "").strip()
                if content:
                    snippet_limit = min(320, summary_char_limit)
                    snippets.append(
                        f"{message.get('role', 'message')}: {content[:snippet_limit]}"
                    )
                if sum(len(item) for item in snippets) >= summary_char_limit:
                    break
            summary = {
                "role": "system",
                "content": build_compacted_history_summary(
                    " | ".join(reversed(snippets))
                ),
            }
            selected = [
                messages[index]
                for index in range(len(messages))
                if index in selected_indices
            ]
            system_count = sum(
                1
                for message in selected
                if str(message.get("role") or "") in {"system", "developer"}
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
    usage = compute_context_usage(request, provider=provider)
    usable = usage.usable_prompt_budget_tokens
    if usable is None:
        usable = _positive_int(request.metadata.get("application_input_token_ceiling")) or UNKNOWN_MODEL_INPUT_CEILING
    if usage.estimated_input_tokens <= usable:
        return request
    message_budget = max(
        0,
        usable - usage.tool_schema_tokens - usage.response_schema_tokens,
    )
    messages, compacted = _compact_messages(request.messages, message_budget)
    if not messages:
        raise LLMContextLimitError(
            provider=provider,
            model=request.model,
            stage="context_preparation",
            detail=(
                "The system instructions, current turn, and required tool results exceed "
                f"the usable prompt budget of {usable:,} tokens for {request.model}."
            ),
            context_usage=usage.to_dict(),
        )
    metadata = dict(_request_metadata(request))
    metadata["_context_compaction_applied"] = compacted
    prepared = replace(request, messages=messages, metadata=metadata)
    prepared_usage = compute_context_usage(prepared, provider=provider)
    if prepared_usage.estimated_input_tokens > usable:
        raise LLMContextLimitError(
            provider=provider,
            model=request.model,
            stage="context_preparation",
            detail=(
                "The required conversation context still exceeds the usable prompt budget "
                f"of {usable:,} tokens for {request.model}."
            ),
            context_usage=prepared_usage.to_dict(),
        )
    return prepared
