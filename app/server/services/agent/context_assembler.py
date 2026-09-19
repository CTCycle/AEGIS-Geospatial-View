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
# in their authoritative stores.  Known model capacity is the source of truth;
# only the protocol/output reserve below is deducted.
UNKNOWN_MODEL_WORKING_SET_CEILING = 32_768
_MESSAGE_PROJECTION_KEYS = (
    "id",
    "turn_index",
    "role",
    "content",
    "type",
    "name",
    "call_id",
    "callId",
    "tool_call_id",
    "tool_calls",
    "arguments",
    "output",
)
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
        bounded_map_memory = _bounded_map_memory(map_memory)
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
            context_window
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
                    item[key]
                    if key == "content" and isinstance(item[key], str)
                    else _bounded_json_value(item[key], depth=0)
                )
                for key in _MESSAGE_PROJECTION_KEYS
                if key in item
            }
            projected.append(projected_item)
            # A very large source message must not become admissible merely
            # because its content was shortened for the model projection.  The
            # source cost is measured from the original selected fields and the
            # projected content remains verbatim whenever the whole item fits.
            source_costs.append(
                estimate_json_tokens(
                    {
                        key: item[key]
                        for key in _MESSAGE_PROJECTION_KEYS
                        if key in item
                    }
                )
            )
        groups = _message_groups(projected)
        included_group_indices: list[int] = []
        included_tokens = 0
        for group_index in range(len(groups) - 1, -1, -1):
            group = groups[group_index]
            group_cost = sum(
                estimate_json_tokens(projected[index]) for index in group
            )
            source_cost = sum(source_costs[index] for index in group)
            if source_cost > raw_capacity or included_tokens + group_cost > raw_capacity:
                # An oversized item should not prevent later inspection of
                # smaller, relevant history entries.  A call/result group is
                # considered one unit so its members can never be split.
                continue
            included_group_indices.append(group_index)
            included_tokens += group_cost
        included_indices = sorted(
            index
            for group_index in included_group_indices
            for index in groups[group_index]
        )
        included = [projected[index] for index in included_indices]
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
        summary_through = int(
            prior_summary.get("through_turn_index") or 0
            if isinstance(prior_summary, dict)
            else 0
        )
        if omitted:
            summary_through = max(
                summary_through,
                max(int(item.get("turn_index") or 0) for item in omitted),
            )
            prior_facts = (
                list(json_array(prior_summary.get("turn_facts")))
                if isinstance(prior_summary, dict)
                else []
            )
            merged_facts = [
                item for item in [*prior_facts, *omitted[-12:]]
                if is_json_object(item)
            ]
            seen_facts: set[tuple[object, str, str]] = set()
            facts: list[dict[str, Any]] = []
            for item in merged_facts:
                key = (
                    item.get("turn_index"),
                    str(item.get("role") or ""),
                    str(item.get("content") or "")[:500],
                )
                if key in seen_facts:
                    continue
                seen_facts.add(key)
                facts.append(
                    {
                        "turn_index": item.get("turn_index"),
                        "role": item.get("role"),
                        "content": str(item.get("content") or "")[:500],
                    }
                )
            summary = {
                "source_message_ids": list(
                    dict.fromkeys(
                        [
                            *(
                                list(json_array(prior_summary.get("source_message_ids")))
                                if isinstance(prior_summary, dict)
                                else []
                            ),
                            *omitted_ids,
                        ]
                    )
                )[-64:],
                "through_turn_index": summary_through,
                "turn_facts": facts[-24:],
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
                "pair_safe": True,
                "message_groups": len(groups),
                "mandatory_overflow": False,
            },
        )


###############################################################################
def _bounded_object(value: object) -> dict[str, Any]:
    bounded = _bounded_json_value(value, depth=0)
    return bounded if is_json_object(bounded) else {}


###############################################################################
def _bounded_map_memory(value: object) -> dict[str, Any]:
    """Keep active overlay identity usable for typed map lifecycle actions."""

    bounded = _bounded_object(value)
    if not is_json_object(value):
        return bounded
    active = value.get("active_visualization")
    if not is_json_object(active):
        return bounded
    overlay_collection = active.get("overlay_collection")
    if not is_json_object(overlay_collection):
        return bounded
    active_bounded = bounded.get("active_visualization")
    if not is_json_object(active_bounded):
        active_bounded = {}
    compact_instances: list[dict[str, Any]] = []
    raw_instances = overlay_collection.get("instances")
    if is_json_array(raw_instances):
        for raw_instance in list(raw_instances)[:32]:
            if not is_json_object(raw_instance):
                continue
            descriptor = raw_instance.get("descriptor")
            descriptor = descriptor if is_json_object(descriptor) else {}
            instance_id = str(
                raw_instance.get("instance_id")
                or descriptor.get("instance_id")
                or ""
            ).strip()
            if not instance_id:
                continue
            capability_id = str(
                raw_instance.get("capability_id")
                or descriptor.get("capability_id")
                or ""
            ).strip()
            label = str(
                descriptor.get("label")
                or raw_instance.get("label")
                or capability_id
                or instance_id
            ).strip()
            compact_instances.append(
                {
                    "instance_id": instance_id,
                    "capability_id": capability_id,
                    "label": label,
                    "visible": bool(raw_instance.get("visible", True)),
                    "opacity": raw_instance.get("opacity", 1.0),
                }
            )
    active_bounded["overlay_collection"] = {
        "revision": overlay_collection.get("revision", 0),
        "instances": compact_instances,
    }
    bounded["active_visualization"] = active_bounded
    return bounded


###############################################################################
def select_pair_safe_messages(
    messages: list[dict[str, Any]],
    *,
    max_items: int | None = None,
    require_complete_pairs: bool = True,
) -> list[dict[str, Any]]:
    """Select a bounded message window without splitting tool exchanges.

    OpenAI Responses items identify calls with ``call_id`` while chat
    completions commonly use an assistant ``tool_calls`` array plus ``tool``
    messages.  The grouping logic understands both forms and keeps all
    members of a call/result exchange together.  Orphan results are omitted
    from protocol windows; ordinary semantic history may opt out of that
    strictness with ``require_complete_pairs=False``.
    """

    groups = _message_groups(messages)
    eligible: list[list[int]] = []
    for group in groups:
        if require_complete_pairs and not _group_is_pair_safe(messages, group):
            continue
        eligible.append(group)
    selected: list[list[int]] = []
    remaining = max_items if max_items is not None else None
    for group in reversed(eligible):
        size = len(group)
        if remaining is not None and selected and size > remaining:
            if _group_has_tool_exchange(messages, group):
                # A complete exchange is more valuable than an older
                # singleton that happened to consume the final slot.  Keep
                # the recent suffix plus the whole pair rather than selecting
                # an invalid partial continuation or unrelated history.
                selected.append(group)
                break
            continue
        if remaining is not None and not selected and size > remaining:
            # Never return half of an active exchange.  The group may exceed a
            # very small requested window, but preserving the pair is safer
            # than sending an invalid provider continuation.
            selected.append(group)
            remaining = 0
            continue
        selected.append(group)
        if remaining is not None:
            remaining -= size
            if remaining <= 0:
                break
    selected_indices = sorted(index for group in selected for index in group)
    return [messages[index] for index in selected_indices]


###############################################################################
def _message_groups(messages: list[dict[str, Any]]) -> list[list[int]]:
    """Build stable connected components for call/result message exchanges."""

    parents = list(range(len(messages)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(first: int, second: int) -> None:
        left, right = find(first), find(second)
        if left != right:
            parents[right] = left

    key_indices: dict[str, list[int]] = {}
    for index, message in enumerate(messages):
        for key in _message_call_ids(message):
            key_indices.setdefault(key, []).append(index)
    for indices in key_indices.values():
        for index in indices[1:]:
            union(indices[0], index)

    # A Responses reasoning item is protocol context for the immediately
    # following function call.  Keep it with that exchange even though it has
    # no call id of its own.
    for index in range(len(messages) - 1):
        if (
            str(messages[index].get("type") or "") == "reasoning"
            and str(messages[index + 1].get("type") or "") == "function_call"
        ):
            union(index, index + 1)

    grouped: dict[int, list[int]] = {}
    for index in range(len(messages)):
        grouped.setdefault(find(index), []).append(index)
    return sorted(grouped.values(), key=lambda item: item[0])


###############################################################################
def _message_call_ids(message: dict[str, Any]) -> list[str]:
    """Return call identifiers present in one request or result item."""

    values: list[str] = []
    message_type = str(message.get("type") or "")
    role = str(message.get("role") or "")
    if message_type in {"function_call", "function_call_output"}:
        for key in ("call_id", "callId", "tool_call_id", "id"):
            value = message.get(key)
            if value is not None and str(value).strip():
                values.append(str(value).strip())
                break
    if role == "tool":
        for key in ("tool_call_id", "call_id", "callId"):
            value = message.get(key)
            if value is not None and str(value).strip():
                values.append(str(value).strip())
                break
    if role == "assistant" and is_json_array(message.get("tool_calls")):
        for raw_call in cast(list[object], message["tool_calls"]):
            if not is_json_object(raw_call):
                continue
            for key in ("id", "call_id", "callId"):
                value = raw_call.get(key)
                if value is not None and str(value).strip():
                    values.append(str(value).strip())
                    break
    return list(dict.fromkeys(values))


###############################################################################
def _group_is_pair_safe(messages: list[dict[str, Any]], group: list[int]) -> bool:
    call_ids: set[str] = set()
    result_ids: set[str] = set()
    for index in group:
        message = messages[index]
        message_type = str(message.get("type") or "")
        role = str(message.get("role") or "")
        ids = set(_message_call_ids(message))
        if message_type == "function_call_output" or role == "tool":
            result_ids.update(ids)
        elif message_type == "function_call" or role == "assistant" and message.get("tool_calls"):
            call_ids.update(ids)
    if not call_ids and not result_ids:
        return True
    # A group made from an assistant tool call and all matching results is
    # valid.  Reasoning-only items remain valid semantic context.
    return bool(call_ids) and call_ids == result_ids


###############################################################################
def _group_has_tool_exchange(messages: list[dict[str, Any]], group: list[int]) -> bool:
    return any(
        str(messages[index].get("type") or "")
        in {"function_call", "function_call_output"}
        or str(messages[index].get("role") or "") in {"assistant", "tool"}
        and bool(messages[index].get("tool_calls"))
        for index in group
    )


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


###############################################################################
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


###############################################################################
def json_text(value: object) -> str:
    try:
        return str(value) if isinstance(value, str) else json.dumps(value, default=str)
    except Exception:
        return str(value)


###############################################################################
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


###############################################################################
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
