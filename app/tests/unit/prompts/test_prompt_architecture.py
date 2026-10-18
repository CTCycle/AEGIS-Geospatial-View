from __future__ import annotations

from importlib import import_module

from server.prompts.agent import (
    build_native_agent_system_prompt,
    build_native_context_messages,
)
from server.prompts.context import build_compacted_history_summary
from server.prompts.providers import build_deepseek_json_schema_instruction


###############################################################################
def test_native_prompt_modules_are_importable_without_legacy_prompt_modules() -> None:
    assert import_module("server.prompts.agent")
    assert import_module("server.prompts.context")
    assert import_module("server.prompts.providers")


###############################################################################
def test_native_system_prompt_owns_loop_safety_and_grounding_rules() -> None:
    prompt = build_native_agent_system_prompt()

    assert "Do not repeat a successful equivalent call." in prompt
    assert "Preserve source conflicts and stale/partial status" in prompt
    assert "Never use transform_evidence to" in prompt
    assert "State that evidence is insufficient" in prompt


###############################################################################
def test_native_context_projection_carries_canonical_state_and_observations() -> None:
    messages = build_native_context_messages(
        current_user_message="Show rainfall around Lugano.",
        recent_messages=[{"role": "assistant", "content": "Prior answer."}],
        active_directives=[{"directive_id": "d1", "text": "Exclude motorways."}],
        task_state={"conversation_id": "conversation-1", "revision": 4},
        map_memory={"active_location": {"label": "Lugano"}},
        summary={"text": "Rainfall was requested previously."},
        relevant_tool_outcomes=[{"evidence_id": "e1", "summary": "Rainfall data."}],
        recent_observations=[{"tool_name": "inspect_evidence", "status": "success"}],
        policy_constraints={"allowed_tool_names": ["inspect_evidence"]},
    )

    assert messages[0]["role"] == "system"
    context = messages[-2]["content"]
    assert "CANONICAL_NATIVE_CONTEXT" in context
    assert "Exclude motorways." in context
    assert "inspect_evidence" in context
    assert messages[-1] == {"role": "user", "content": "Show rainfall around Lugano."}


###############################################################################
def test_shared_prompt_helpers_render_without_unresolved_placeholders() -> None:
    assert "{summary}" not in build_compacted_history_summary("older turn")
    assert "{schema_json}" not in build_deepseek_json_schema_instruction({"type": "object"})
