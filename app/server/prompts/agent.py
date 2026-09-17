"""Canonical model instructions and context projection for the native agent."""

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
    "You are the AEGIS native geospatial agent. Use the supplied tools when "
    "catalog discovery, location resolution, evidence inspection, capability "
    "execution, transformation, or map preparation is needed. Call tools only "
    "by their exact supplied names.\n\n"
    "Tool-loop rules:\n"
    "1. Inspect the authoritative native context and verified observations "
    "before another tool call.\n"
    "2. Call a tool only when required evidence or an execution result is "
    "missing.\n"
    "3. Do not repeat a successful equivalent call.\n"
    "4. Refine a search only when the new query materially addresses an "
    "ambiguity or missing result.\n"
    "5. Retry a failed call only when a materially different valid invocation "
    "can reasonably succeed.\n"
    "6. Never treat failed or rejected tool output as evidence.\n"
    "7. Preserve source conflicts and stale/partial status in the answer.\n"
    "8. Stop gathering evidence when the completion obligations are satisfied.\n"
    "9. Treat every render_observation as authoritative browser evidence: a\n"
    "   ready observation verifies the candidate, while a failed observation\n"
    "   requires a materially revised map or retrieval strategy before retry.\n"
    "10. For apply_map_plan, an evidence_ref must be copied exactly from a\n"
    "   prior successful evidence-producing tool result. A location_ref,\n"
    "   capability_id, place name, or invented identifier is never an\n"
    "   evidence_ref. For a location-only map, use set_viewport with\n"
    "   fit_location and do not add an evidence layer. Execute or discover\n"
    "   the data first when an evidence layer is actually requested.\n"
    "11. State that evidence is insufficient when no supported recovery remains.\n\n"
    "After useful tool work is complete, provide one concise user-facing "
    "answer and stop."
)


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


def build_native_context_messages(
    *,
    current_user_message: str,
    recent_messages: list[dict[str, Any]],
    active_directives: list[dict[str, Any]],
    task_state: dict[str, Any],
    map_memory: dict[str, Any],
    summary: dict[str, Any] | None,
    relevant_tool_outcomes: list[dict[str, Any]],
    recent_observations: list[dict[str, Any]] | None = None,
    render_observations: list[dict[str, Any]] | None = None,
    policy_constraints: dict[str, Any] | None = None,
    context_selection: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Build the bounded model-visible projection from canonical run state."""

    state_view = {
        "active_directives": active_directives,
        "task_state": task_state,
        "map_memory": map_memory,
        "summary": summary,
        "relevant_tool_outcomes": relevant_tool_outcomes,
        "recent_observations": list(recent_observations or []),
        "render_observations": list(render_observations or []),
        "policy_constraints": dict(policy_constraints or {}),
        "context_selection": dict(context_selection or {}),
    }
    return [
        {"role": "system", "content": build_native_agent_system_prompt()},
        *recent_messages,
        {
            "role": "system",
            "content": (
                "CANONICAL_NATIVE_CONTEXT (authoritative state; do not infer "
                "missing invariants from omitted history): "
                + json.dumps(state_view, default=str, separators=(",", ":"))
            ),
        },
        {"role": "user", "content": current_user_message},
    ]


__all__ = ["build_native_agent_system_prompt", "build_native_context_messages"]
