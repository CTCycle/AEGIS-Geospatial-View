from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any, Literal, cast

from server.common.typing import is_json_array, is_json_object, json_array

from server.domain.agent.context import AgentContextPackage, ConversationDirective
from server.services.llm.context_budget import (
    estimate_json_tokens,
    resolve_model_context_profile,
)
from server.services.llm.errors import LLMContextLimitError

if TYPE_CHECKING:
    from server.services.llm.context_profile_resolver import ModelContextProfileResolver

# History is a linguistic projection; geometry and execution payloads remain
# in their authoritative stores. This cap is independent of model capacity.
KNOWN_MODEL_WORKING_SET_CEILING = 64_000
UNKNOWN_MODEL_WORKING_SET_CEILING = 32_768
type BoundedJson = (
    None
    | bool
    | int
    | float
    | str
    | dict[str, "BoundedJson"]
    | list["BoundedJson"]
)

###############################################################################
class AgentContextAssembler:

    # -------------------------------------------------------------------------
    def __init__(
        self,
        context_profile_resolver: ModelContextProfileResolver | None = None,
    ) -> None:
        self.context_profile_resolver = context_profile_resolver

    # -------------------------------------------------------------------------
    def assemble(
        self,
        *,
        provider: str,
        model: str,
        current_user_message: str,
        messages: list[dict[str, Any]],
        directives: list[ConversationDirective],
        task_state: dict[str, Any],
        map_memory: dict[str, Any],
        prior_summary: dict[str, Any] | None = None,
        relevant_tool_outcomes: list[dict[str, Any]] | None = None,
        policy_constraints: dict[str, Any] | None = None,
        phase: Literal["native_loop"] = "native_loop",
    ) -> AgentContextPackage:
        profile = (
            self.context_profile_resolver.resolve(provider, model)
            if self.context_profile_resolver is not None
            else resolve_model_context_profile(provider, model)
        )
        context_window = profile.context_window_tokens if profile else None
        output_reserve = (
            (profile.maximum_output_tokens or profile.default_output_reserve)
            if profile
            else None
        )
        raw_outcomes: list[dict[str, Any]] = []
        for item in relevant_tool_outcomes or []:
            bounded_outcome = _bounded_json_value(item, depth=0)
            if is_json_object(bounded_outcome):
                raw_outcomes.append(bounded_outcome)
        constraints = _bounded_object(policy_constraints or {})
        bounded_task_state = _bounded_object(task_state)
        bounded_map_memory = _bounded_object(map_memory)
        outcomes = _select_relevant_outcomes(
            raw_outcomes,
            current_user_message=current_user_message,
            task_state=bounded_task_state,
            map_memory=bounded_map_memory,
        )
        bounded_instructions = [
            _bounded_json_value(
                item.model_dump(mode="json"),
                depth=0,
            )
            for item in directives
        ]
        mandatory = {
            "current_user_message": str(current_user_message)[:12_000],
            "active_directives": bounded_instructions,
            "task_state": bounded_task_state,
            "map_memory": bounded_map_memory,
            "policy_constraints": constraints,
        }
        mandatory_tokens = estimate_json_tokens(mandatory)
        application_ceiling = (
            min(context_window, KNOWN_MODEL_WORKING_SET_CEILING)
            if context_window is not None
            else UNKNOWN_MODEL_WORKING_SET_CEILING
        )
        output_reserve_value = output_reserve or 0
        application_usable = (
            application_ceiling - output_reserve_value - 512
            if output_reserve_value < application_ceiling
            else application_ceiling - 512
        )
        model_usable = (
            context_window - output_reserve_value - 512
            if context_window is not None
            else application_usable
        )
        usable = max(0, min(application_usable, model_usable))
        if mandatory_tokens > usable:
            raise LLMContextLimitError(
                provider=provider,
                model=model,
                stage="context_assembly",
                detail=(
                    "The mandatory agent state exceeds the usable prompt budget "
                    f"of {usable:,} tokens for {model}."
                ),
            )
        working_budget = max(0, usable - mandatory_tokens)
        evidence_budget = working_budget * 50 // 100
        raw_budget = working_budget * 35 // 100
        summary_budget = working_budget - evidence_budget - raw_budget
        selected_outcomes_reversed: list[dict[str, Any]] = []
        outcome_tokens = 0
        for outcome in reversed(outcomes):
            cost = estimate_json_tokens(outcome)
            if outcome_tokens + cost > evidence_budget:
                continue
            selected_outcomes_reversed.append(outcome)
            outcome_tokens += cost
        selected_outcomes = list(reversed(selected_outcomes_reversed))
        raw_capacity = raw_budget + max(0, evidence_budget - outcome_tokens)
        projected: list[dict[str, Any]] = []
        source_costs: list[int] = []
        for item in messages:
            projected_item = {
                key: (
                    str(item[key])[:4_000]
                    if key == "content"
                    else item[key]
                )
                for key in ("id", "turn_index", "role", "content")
                if key in item
            }
            projected.append(projected_item)
            # A very large source message must not become admissible merely
            # because its content was shortened for the model projection.
            source_costs.append(
                estimate_json_tokens(
                    {
                        key: item[key]
                        for key in ("id", "turn_index", "role", "content")
                        if key in item
                    }
                )
            )
        included_reversed: list[dict[str, Any]] = []
        included_indices: list[int] = []
        included_tokens = 0
        for index in range(len(projected) - 1, -1, -1):
            message = projected[index]
            cost = estimate_json_tokens(message)
            if (
                source_costs[index] > raw_capacity
                or included_tokens + cost > raw_capacity
            ):
                # An oversized item should not prevent later inspection of
                # smaller, relevant history entries.
                continue
            included_reversed.append(message)
            included_indices.append(index)
            included_tokens += cost
        included = list(reversed(included_reversed))
        included_indices.sort()
        included_ids = [
            int(item["id"]) for item in included if isinstance(item.get("id"), int)
        ]
        included_index_set = set(included_indices)
        omitted = [
            item for index, item in enumerate(projected) if index not in included_index_set
        ]
        omitted_ids = [
            int(item["id"]) for item in omitted if isinstance(item.get("id"), int)
        ]
        summary_capacity = summary_budget + max(0, raw_capacity - included_tokens)
        summary: dict[str, Any] | None = prior_summary
        summary_through = 0
        if omitted:
            summary_through = max(int(item.get("turn_index") or 0) for item in omitted)
            summary = {
                "source_message_ids": omitted_ids,
                "through_turn_index": summary_through,
                "turn_facts": [
                    {
                        "turn_index": item.get("turn_index"),
                        "role": item.get("role"),
                        "content": str(item.get("content") or "")[:500],
                    }
                    for item in omitted[-12:]
                ],
            }
        if summary is not None:
            # Never mutate a persisted summary supplied by the caller.
            facts = list(json_array(summary.get("turn_facts")))[-12:]
            summary = {
                "through_turn_index": summary.get(
                    "through_turn_index", summary_through
                ),
                "turn_facts": facts,
            }
            while facts and estimate_json_tokens(summary) > summary_capacity:
                facts.pop(0)
            if estimate_json_tokens(summary) > summary_capacity:
                summary = None
        return AgentContextPackage(
            current_user_message=current_user_message,
            active_directives=directives,
            task_state=bounded_task_state,
            map_memory=bounded_map_memory,
            summary=summary,
            recent_messages=included,
            relevant_tool_outcomes=selected_outcomes,
            policy_constraints=constraints,
            included_message_ids=included_ids,
            summarized_through_turn_index=summary_through,
            omitted_message_ids=omitted_ids,
            context_allocation={
                "phase": phase,
                "model": model,
                "estimator_source": "model_profile" if profile is not None else "conservative_chars_per_token",
                "usable_input_tokens": usable,
                "mandatory_tokens": mandatory_tokens,
                "evidence_budget": evidence_budget,
                "evidence_tokens": outcome_tokens,
                "conversation_budget": raw_capacity,
                "conversation_tokens": included_tokens,
                "summary_budget": summary_capacity,
                "summary_tokens": estimate_json_tokens(summary) if summary is not None else 0,
                "response_reserve_tokens": output_reserve or 0,
                "safety_tokens": 512,
                "compacted_ids": omitted_ids,
                "mandatory_overflow": False,
            },
        )


def _bounded_object(value: object) -> dict[str, Any]:
    bounded = _bounded_json_value(value, depth=0)
    return bounded if is_json_object(bounded) else {}


_RELEVANCE_STOP_WORDS = frozenset(
    {
        "about",
        "after",
        "around",
        "from",
        "into",
        "that",
        "their",
        "there",
        "this",
        "with",
        "within",
    }
)


def _select_relevant_outcomes(
    outcomes: list[dict[str, Any]],
    *,
    current_user_message: str,
    task_state: dict[str, Any],
    map_memory: dict[str, Any],
) -> list[dict[str, Any]]:
    """Keep durable evidence available while narrowing the immediate view.

    The evidence repository remains the source of truth.  This projection only
    chooses what belongs in the next model request, using the current request,
    canonical goal/scope, explicit references, and recency.
    """

    if len(outcomes) <= 1:
        return outcomes
    seed_text = " ".join(
        [
            current_user_message,
            json_text(task_state.get("goal")),
            json_text(task_state.get("route")),
            json_text(task_state.get("constraints")),
            json_text(map_memory),
        ]
    )
    terms = {
        token
        for token in re.findall(r"[a-z0-9][a-z0-9_-]+", seed_text.casefold())
        if len(token) > 2 and token not in _RELEVANCE_STOP_WORDS
    }
    explicit_refs = {
        str(value)
        for value in _walk_values(task_state, keys={"evidence_refs", "evidence_id"})
        if str(value).strip()
    }
    ranked: list[tuple[float, int, dict[str, Any]]] = []
    for index, outcome in enumerate(outcomes):
        text = json_text(outcome).casefold()
        score = float(sum(1 for term in terms if term in text))
        if explicit_refs and any(ref.casefold() in text for ref in explicit_refs):
            score += 100.0
        score += min(10.0, index / max(1, len(outcomes)))
        ranked.append((score, index, outcome))
    ranked.sort(key=lambda item: (-item[0], -item[1]))
    selected = {index for _, index, _ in ranked[: min(32, len(ranked))]}
    return [item for index, item in enumerate(outcomes) if index in selected]


def json_text(value: object) -> str:
    try:
        return str(value) if isinstance(value, str) else json.dumps(value, default=str)
    except Exception:
        return str(value)


def _walk_values(value: object, *, keys: set[str]) -> list[object]:
    found: list[object] = []
    if is_json_object(value):
        for key, child in value.items():
            if key in keys:
                if is_json_array(child):
                    found.extend(cast(list[object], child))
                else:
                    found.append(child)
            found.extend(_walk_values(child, keys=keys))
    elif is_json_array(value):
        for child in value:
            found.extend(_walk_values(child, keys=keys))
    return found


def _bounded_json_value(
    value: object,
    *,
    depth: int,
    max_depth: int = 4,
    list_limit: int = 24,
    key_limit: int = 32,
    string_limit: int = 800,
) -> BoundedJson:
    """Bound structured context without ever producing partial JSON."""

    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:string_limit]
    if depth >= max_depth:
        return "[truncated]"
    if is_json_object(value):
        return {
            key: _bounded_json_value(
                child,
                depth=depth + 1,
                max_depth=max_depth,
                list_limit=list_limit,
                key_limit=key_limit,
                string_limit=string_limit,
            )
            for key, child in list(value.items())[:key_limit]
        }
    if is_json_array(value):
        return [
            _bounded_json_value(
                child,
                depth=depth + 1,
                max_depth=max_depth,
                list_limit=list_limit,
                key_limit=key_limit,
                string_limit=string_limit,
            )
            for child in list(value)[:list_limit]
        ]
    if isinstance(value, tuple):
        items = list(cast(tuple[object, ...], value))
        return [
            _bounded_json_value(
                child,
                depth=depth + 1,
                max_depth=max_depth,
                list_limit=list_limit,
                key_limit=key_limit,
                string_limit=string_limit,
            )
            for child in items[:list_limit]
        ]
    return str(value)[:string_limit]
