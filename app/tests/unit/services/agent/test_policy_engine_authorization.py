from __future__ import annotations

from server.domain.extraction.models import (
    ConversationContextSnapshot,
    DisallowedPattern,
    LocationSignal,
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


def test_evaluate_preflight_rejects_unknown_task_class() -> None:
    turn = TurnParseResult(
        user_text="do something odd",
        conversation_context=ConversationContextSnapshot(),
        task_class="unclear",
        normalized_action=NormalizedAction(
            action_id="unknown",
            action_label="Unknown",
            requires_location=False,
        ),
    )

    result = _engine().evaluate_preflight(turn)

    assert result is not None
    assert result.plan.state == "reject"
    assert result.clarification is not None
    assert result.clarification.missing_fields == ["task"]


def test_evaluate_preflight_clarifies_missing_location() -> None:
    turn = TurnParseResult(
        user_text="show weather",
        conversation_context=ConversationContextSnapshot(),
        task_class="map_search",
        normalized_action=NormalizedAction(
            action_id="map_search",
            action_label="Map Search",
            requires_location=True,
        ),
        location_signals=[],
    )

    result = _engine().evaluate_preflight(turn)

    assert result is not None
    assert result.plan.state == "clarify"
    assert result.clarification is not None
    assert result.clarification.missing_fields == ["location"]


def test_evaluate_preflight_rejects_blocked_patterns() -> None:
    turn = TurnParseResult(
        user_text="bypass policy",
        conversation_context=ConversationContextSnapshot(),
        task_class="direct_query",
        normalized_action=NormalizedAction(
            action_id="direct_query",
            action_label="Direct Query",
            requires_location=False,
        ),
        disallowed_patterns=[
            DisallowedPattern(
                pattern_id="policy_bypass",
                reason="Policy bypass attempt.",
                matched_text="ignore policy",
            )
        ],
    )

    result = _engine().evaluate_preflight(turn)

    assert result is not None
    assert result.plan.state == "reject"
    assert result.clarification is not None
    assert "Policy bypass attempt." in result.clarification.reason


def test_evaluate_preflight_passes_valid_request() -> None:
    turn = TurnParseResult(
        user_text="show Rome",
        conversation_context=ConversationContextSnapshot(memory_snapshot={"active_location": {"label": "Rome"}}),
        task_class="map_search",
        normalized_action=NormalizedAction(
            action_id="map_search",
            action_label="Map Search",
            requires_location=True,
        ),
        location_signals=[
            LocationSignal(
                signal_type="city",
                raw_value="Rome",
                normalized_value="Rome",
            )
        ],
    )

    assert _engine().evaluate_preflight(turn) is None
