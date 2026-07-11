from __future__ import annotations

from typing import Any

from server.domain.agent.context import AgentContextPackage, ConversationDirective
from server.services.llm.cloud_catalog import get_model_context_profile
from server.services.llm.context_budget import estimate_json_tokens


class AgentContextAssembler:
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
        profile = get_model_context_profile(provider, model)
        context_window = profile.context_window_tokens if profile else 8192
        output_reserve = profile.default_output_reserve if profile else 2048
        usable = max(1024, context_window - output_reserve - 512)
        mandatory = {
            "current_user_message": current_user_message,
            "active_instructions": [item.model_dump(mode="json") for item in directives],
            "task_state": task_state,
            "map_memory": map_memory,
        }
        mandatory_tokens = estimate_json_tokens(mandatory)
        if mandatory_tokens > usable:
            raise ValueError("Mandatory conversation state exceeds the selected model limit.")
        raw_budget = max(0, int(usable * 0.6) - mandatory_tokens)
        included: list[dict[str, Any]] = []
        included_tokens = 0
        for message in reversed(messages):
            cost = estimate_json_tokens(message)
            if included and included_tokens + cost > raw_budget:
                break
            included.append(message)
            included_tokens += cost
        included.reverse()
        included_ids = [int(item["id"]) for item in included if isinstance(item.get("id"), int)]
        omitted = [item for item in messages if item not in included]
        omitted_ids = [int(item["id"]) for item in omitted if isinstance(item.get("id"), int)]
        summary = prior_summary
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
        tool_outcomes = [
            {
                "message_id": item.get("id"),
                "turn_index": item.get("turn_index"),
                "tool_payload": item.get("tool_payload"),
            }
            for item in included
            if item.get("tool_payload")
        ]
        return AgentContextPackage(
            current_user_message=current_user_message,
            active_instructions=directives,
            task_state=task_state,
            map_memory=map_memory,
            conversation_summary=summary,
            recent_messages=included,
            relevant_tool_outcomes=tool_outcomes,
            included_message_ids=included_ids,
            summarized_through_turn_index=summary_through,
            omitted_message_ids=omitted_ids,
        )
