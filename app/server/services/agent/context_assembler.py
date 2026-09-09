from __future__ import annotations

from typing import TYPE_CHECKING, Any
from server.common.typing import json_array

from server.domain.agent.context import AgentContextPackage, ConversationDirective
from server.services.llm.context_budget import (
    estimate_json_tokens,
    resolve_model_context_profile,
)
from server.services.llm.errors import LLMContextLimitError
from server.domain.agent.runtime import compact_task_context

if TYPE_CHECKING:
    from server.services.llm.context_profile_resolver import ModelContextProfileResolver

# History is a linguistic projection; geometry and execution payloads remain
# in their authoritative stores. This cap is independent of model capacity.
KNOWN_MODEL_WORKING_SET_CEILING = 64_000
UNKNOWN_MODEL_WORKING_SET_CEILING = 32_768

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
        outcomes = list(relevant_tool_outcomes or [])
        mandatory = {
            "current_user_message": current_user_message,
            "active_instructions": [
                item.model_dump(mode="json") for item in directives
            ],
            "task_state": compact_task_context(task_state),
            "map_memory": map_memory,
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
        selected_outcomes: list[dict[str, Any]] = []
        outcome_tokens = 0
        for outcome in outcomes:
            cost = estimate_json_tokens(outcome)
            if outcome_tokens + cost > evidence_budget:
                break
            selected_outcomes.append(outcome)
            outcome_tokens += cost
        raw_capacity = raw_budget + max(0, evidence_budget - outcome_tokens)
        projected = [
            {
                key: item[key]
                for key in ("id", "turn_index", "role", "content")
                if key in item
            }
            for item in messages
        ]
        included: list[dict[str, Any]] = []
        included_tokens = 0
        for message in reversed(projected):
            cost = estimate_json_tokens(message)
            if included_tokens + cost > raw_capacity:
                break
            included.append(message)
            included_tokens += cost
        included.reverse()
        included_ids = [
            int(item["id"]) for item in included if isinstance(item.get("id"), int)
        ]
        omitted = projected[: len(projected) - len(included)]
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
            active_instructions=directives,
            task_state=compact_task_context(task_state),
            map_memory=map_memory,
            conversation_summary=summary,
            recent_messages=included,
            relevant_tool_outcomes=selected_outcomes,
            included_message_ids=included_ids,
            summarized_through_turn_index=summary_through,
            omitted_message_ids=omitted_ids,
            context_allocation={
                "phase": "parser",
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
