from __future__ import annotations

from server.domain.extraction.models import (
    ConversationContextSnapshot,
    NormalizedAction,
    TurnParseResult,
)
from server.services.agent.native_tool_loop import AgentExecutionContext
from server.services.agent.policy_engine import PolicyEngine


def _engine() -> PolicyEngine:
    return PolicyEngine.__new__(PolicyEngine)


def test_policy_constraints_include_catalog_tools_only() -> None:
    turn = TurnParseResult(
        user_text="show Rome",
        conversation_context=ConversationContextSnapshot(),
        task_class="map_search",
        normalized_action=NormalizedAction(
            action_id="map_search",
            action_label="Map Search",
            requires_location=True,
        ),
    )
    constraints = _engine().build_agent_constraints(turn, {})
    assert constraints.allowed_tool_names == [
        "list_geospatial_capabilities",
        "describe_geospatial_capability",
        "execute_geospatial_capability",
    ]


def test_authorize_tool_call_rejects_disallowed_tool() -> None:
    context = AgentExecutionContext(
        policy_constraints={"allowed_tool_names": ["list_geospatial_capabilities"]}
    )
    result = _engine().authorize_tool_call("execute_geospatial_capability", {}, context)
    assert result.allowed is False


def test_validate_tool_result_flags_error_envelope() -> None:
    result = _engine().validate_tool_result(
        "lookup",
        {"ok": False, "error": {"message": "bad input"}},
        AgentExecutionContext(),
    )
    assert result.valid is False
    assert result.reason == "bad input"
