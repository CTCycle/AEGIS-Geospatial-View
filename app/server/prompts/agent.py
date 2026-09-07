"""Prompt declarations and builders for the native geospatial tool loop."""

from __future__ import annotations

import json
from typing import Any

from server.prompts.common import (
    GROUNDING_REQUIREMENTS,
    INTERNAL_INFORMATION_RESTRICTIONS,
    SUPPORTED_AEGIS_SCOPE,
    UNCERTAINTY_RULES,
)

NATIVE_AGENT_SYSTEM_PROMPT = (
    "You are the AEGIS native geospatial agent. Use the provided native tools "
    "when supported catalog discovery, capability description, or execution is "
    "actually needed. Call tools only by their exact supplied names.\n\n"
    "Tool-loop rules:\n"
    "1. Inspect existing verified observations and current map state before "
    "calling another tool.\n"
    "2. Call a tool only when required evidence or an execution result is "
    "missing.\n"
    "3. Do not repeat a successful equivalent call.\n"
    "4. Refine a search only when the new query materially addresses an "
    "ambiguity or missing result.\n"
    "5. Retry a failed call only when a materially different valid invocation "
    "can reasonably succeed.\n"
    "6. Never treat failed or rejected tool output as evidence.\n"
    "7. When sources conflict, preserve the conflict instead of silently "
    "selecting one source.\n"
    "8. Stop gathering evidence when the task is satisfied.\n"
    "9. Stop when no useful supported tool remains.\n"
    "10. State that evidence is insufficient when that is the actual result.\n\n"
    "After the useful tool work is complete, provide one concise user-facing "
    "answer and stop."
)

NATIVE_AGENT_CONTEXT_TEMPLATE = (
    "Parsed request:\n{parsed_request}\n\n"
    "Map memory:\n{memory_snapshot}\n\n"
    "Active conversation instructions:\n{active_instructions}\n\n"
    "Current task state:\n{task_snapshot}\n\n"
    "Policy constraints:\n{policy_constraints}"
)

WORKING_STATE_TEMPLATE = "WORKING_STATE (replaceable): {state_json}"

###############################################################################
def build_native_agent_system_prompt() -> str:
    return "\n\n".join(
        [
            NATIVE_AGENT_SYSTEM_PROMPT,
            SUPPORTED_AEGIS_SCOPE,
            GROUNDING_REQUIREMENTS,
            UNCERTAINTY_RULES,
            INTERNAL_INFORMATION_RESTRICTIONS,
        ]
    )

###############################################################################
def build_native_agent_messages(
    *,
    turn_contract: Any,
    memory_snapshot: dict[str, Any],
    constraints: Any,
    active_instructions: list[dict[str, Any]] | None = None,
    task_snapshot: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    parsed_request = (
        turn_contract.model_dump_json()
        if hasattr(turn_contract, "model_dump_json")
        else json.dumps(turn_contract, default=str)
    )
    context = NATIVE_AGENT_CONTEXT_TEMPLATE.format(
        parsed_request=parsed_request,
        memory_snapshot=memory_snapshot,
        active_instructions=active_instructions or [],
        task_snapshot=task_snapshot or {},
        policy_constraints=constraints,
    )
    return [
        {"role": "system", "content": build_native_agent_system_prompt()},
        {"role": "user", "content": context},
    ]

###############################################################################
def build_working_state_message(
    *,
    parsed_request: Any,
    map_state: dict[str, Any],
    policy_constraints: dict[str, Any],
    completed_tool_results: list[dict[str, Any]],
) -> dict[str, Any]:
    state = {
        "parsed_request": parsed_request,
        "map_state": map_state,
        "policy_constraints": policy_constraints,
        "completed_tool_results": completed_tool_results,
    }
    return {
        "role": "system",
        "content": WORKING_STATE_TEMPLATE.format(
            state_json=json.dumps(state, default=str),
        ),
    }
