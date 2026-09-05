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
HISTORY_TOKEN_CEILING = 8192


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
        mandatory = {
            "current_user_message": current_user_message,
            "active_instructions": [
                item.model_dump(mode="json") for item in directives
            ],
            "task_state": compact_task_context(task_state),
            "map_memory": map_memory,
        }
        mandatory_tokens = estimate_json_tokens(mandatory)
        usable = (
            max(0, context_window - (output_reserve or 0) - 512)
            if context_window is not None
            else 16_384
        )
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
        history_budget = min(HISTORY_TOKEN_CEILING, max(0, usable - mandatory_tokens))
        # Reserve a bounded share for older linguistic context before selecting
        # recent messages; adding a summary afterwards must not exceed budget.
        summary_budget = min(2048, history_budget // 4)
        raw_budget = history_budget - summary_budget
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
            if included_tokens + cost > raw_budget:
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
            while facts and estimate_json_tokens(summary) > summary_budget:
                facts.pop(0)
            if estimate_json_tokens(summary) > summary_budget:
                summary = None
        return AgentContextPackage(
            current_user_message=current_user_message,
            active_instructions=directives,
            task_state=compact_task_context(task_state),
            map_memory=map_memory,
            conversation_summary=summary,
            recent_messages=included,
            relevant_tool_outcomes=[],
            included_message_ids=included_ids,
            summarized_through_turn_index=summary_through,
            omitted_message_ids=omitted_ids,
        )
