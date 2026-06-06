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
from server.services.agent.location_resolver import LocationResolver


class _CapabilityRegistry:
    def __init__(self) -> None:
        self.capabilities = {
            "weather_overlay": {
                "id": "weather_overlay",
                "metadata": {"geometry_type": "point"},
            },
            "coordinates_tool": {
                "id": "coordinates_tool",
                "metadata": {"geometry_type": "not-applicable"},
            },
            "tomtom_traffic_flow": {
                "id": "tomtom_traffic_flow",
                "metadata": {"geometry_type": "raster-grid"},
            },
        }

    def get_capability(self, capability_id: str):
        return self.capabilities.get(capability_id)


class _RuntimeRegistry:
    def provider_health(self, capability_id: str) -> str:
        if capability_id == "tomtom_traffic_flow":
            return "missing_credentials"
        if capability_id == "disabled_overlay":
            return "disabled"
        return "healthy"

    def supports_mode(self, capability_id: str, mode: str) -> bool:
        supported = {
            "weather_overlay": {"map"},
            "coordinates_tool": {"direct_text"},
            "tomtom_traffic_flow": {"map"},
        }
        return mode in supported.get(capability_id, set())


def _engine() -> PolicyEngine:
    return PolicyEngine(
        location_resolver=LocationResolver(),
        capability_registry=_CapabilityRegistry(),  # type: ignore[arg-type]
        runtime_registry=_RuntimeRegistry(),  # type: ignore[arg-type]
    )


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


def test_authorize_capability_execution_rejects_missing_credentials() -> None:
    turn = TurnParseResult(
        user_text="show traffic in Rome",
        conversation_context=ConversationContextSnapshot(
            memory_snapshot={"active_location": {"label": "Rome"}}
        ),
        task_class="map_search",
        normalized_action=NormalizedAction(
            action_id="map_search",
            action_label="Map Search",
            requires_location=True,
        ),
        location_signals=[
            LocationSignal(signal_type="city", raw_value="Rome", normalized_value="Rome")
        ],
    )

    result = _engine().authorize_capability_execution(
        "tomtom_traffic_flow",
        {},
        turn,
        AgentExecutionContext(),
    )

    assert result.allowed is False
    assert result.metadata["code"] == "missing_credentials"


def test_authorize_capability_execution_rejects_mode_mismatch() -> None:
    turn = TurnParseResult(
        user_text="show Rome",
        conversation_context=ConversationContextSnapshot(),
        task_class="map_search",
        normalized_action=NormalizedAction(
            action_id="map_search",
            action_label="Map Search",
            requires_location=True,
        ),
        location_signals=[
            LocationSignal(signal_type="city", raw_value="Rome", normalized_value="Rome")
        ],
    )

    result = _engine().authorize_capability_execution(
        "coordinates_tool",
        {"location": "Rome"},
        turn,
        AgentExecutionContext(),
    )

    assert result.allowed is False
    assert result.metadata["code"] == "unsupported_capability"


def test_authorize_capability_execution_rejects_missing_location_context() -> None:
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

    result = _engine().authorize_capability_execution(
        "weather_overlay",
        {},
        turn,
        AgentExecutionContext(),
    )

    assert result.allowed is False
    assert result.metadata["code"] == "invalid_arguments"


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
