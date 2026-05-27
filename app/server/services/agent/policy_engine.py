from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from server.domain.agent.decision import (
    ClarificationRequest,
    DecisionTrace,
    ExecutionPlan,
    PolicyDecision,
)
from server.domain.extraction.models import TurnParseResult
from server.services.agent.location_resolver import LocationResolver


@dataclass(frozen=True)
class AgentPolicyConstraints:
    requires_location: bool
    blocked_patterns: list[str] = field(default_factory=list)
    allowed_tool_names: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolAuthorizationResult:
    allowed: bool
    reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolValidationResult:
    valid: bool
    reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class PolicyEngine:
    def __init__(
        self,
        *,
        location_resolver: LocationResolver,
        **_: Any,
    ) -> None:
        self.location_resolver = location_resolver

    def evaluate_preflight(self, turn: TurnParseResult) -> PolicyDecision | None:
        trace = DecisionTrace(steps=["1.validate_task_class"])
        task_validation = self._validate_task_class(turn)
        if task_validation is not None:
            return PolicyDecision(
                plan=ExecutionPlan(
                    state="reject",
                    action_id=turn.normalized_action.action_id,
                ),
                clarification=task_validation,
                trace=trace,
            )
        trace.steps.append("2.enforce_location_requirement")
        location_policy = self._enforce_location_policy(turn)
        if location_policy is not None:
            return PolicyDecision(
                plan=ExecutionPlan(
                    state="clarify",
                    action_id=turn.normalized_action.action_id,
                ),
                clarification=location_policy,
                trace=trace,
            )
        trace.steps.append("3.enforce_safety_policy")
        safety_policy = self._enforce_safety_policy(turn)
        if safety_policy is not None:
            return PolicyDecision(
                plan=ExecutionPlan(
                    state="reject",
                    action_id=turn.normalized_action.action_id,
                ),
                clarification=safety_policy,
                trace=trace,
            )
        return None

    def build_agent_constraints(
        self,
        parsed_request: TurnParseResult,
        map_state: dict[str, Any] | None = None,
    ) -> AgentPolicyConstraints:
        actionable_patterns = self._actionable_disallowed_patterns(parsed_request)
        return AgentPolicyConstraints(
            requires_location=parsed_request.normalized_action.requires_location,
            blocked_patterns=[item.pattern_id for item in actionable_patterns],
            allowed_tool_names=[
                "list_geospatial_capabilities",
                "describe_geospatial_capability",
                "execute_geospatial_capability",
            ],
            metadata={"map_state": map_state or {}},
        )

    def authorize_tool_call(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        context: Any,
    ) -> ToolAuthorizationResult:
        _ = arguments
        constraints = getattr(context, "policy_constraints", {}) or {}
        blocked_patterns = constraints.get("blocked_patterns")
        if blocked_patterns:
            return ToolAuthorizationResult(
                allowed=False,
                reason="Request contains blocked policy patterns.",
            )
        allowed = constraints.get("allowed_tool_names")
        if isinstance(allowed, list) and allowed and tool_name not in set(map(str, allowed)):
            return ToolAuthorizationResult(
                allowed=False,
                reason=f"Tool '{tool_name}' is not allowed by policy constraints.",
            )
        return ToolAuthorizationResult(allowed=True)

    def validate_tool_result(
        self,
        tool_name: str,
        result: Any,
        context: Any,
    ) -> ToolValidationResult:
        _ = tool_name, context
        if isinstance(result, dict) and result.get("ok") is False:
            error = result.get("error")
            reason = error.get("message") if isinstance(error, dict) else "Tool failed."
            return ToolValidationResult(valid=False, reason=str(reason))
        return ToolValidationResult(valid=True)

    def _validate_task_class(self, turn: TurnParseResult) -> ClarificationRequest | None:
        if turn.task_class in {"map_search", "direct_query", "general_question"}:
            return None
        return ClarificationRequest(
            question="Can you clarify whether you want a map search or a direct answer?",
            reason="Task class is unclear.",
            missing_fields=["task"],
        )

    def _enforce_location_policy(self, turn: TurnParseResult) -> ClarificationRequest | None:
        if "deictic_without_memory" in turn.ambiguities:
            return ClarificationRequest(
                question="Which location should I use?",
                reason="The request refers to a previous location, but no active location is available.",
                missing_fields=["location"],
            )
        if (
            any(signal.signal_type == "deictic" for signal in turn.location_signals)
            and not turn.conversation_context.memory_snapshot.get("active_location")
        ):
            return ClarificationRequest(
                question="Which location should I use?",
                reason="The request refers to a previous location, but no active location is available.",
                missing_fields=["location"],
            )
        if (
            turn.normalized_action.requires_location
            and not turn.location_signals
            and not turn.conversation_context.memory_snapshot.get("active_location")
        ):
            return ClarificationRequest(
                question="Which location should I use?",
                reason="Location is required for this action.",
                missing_fields=["location"],
            )
        return None

    def _enforce_safety_policy(self, turn: TurnParseResult) -> ClarificationRequest | None:
        actionable_patterns = self._actionable_disallowed_patterns(turn)
        if not actionable_patterns:
            return None
        return ClarificationRequest(
            question="I cannot execute this request with the current policy constraints.",
            reason="; ".join(item.reason for item in actionable_patterns if item.reason),
            missing_fields=[],
        )

    @staticmethod
    def _actionable_disallowed_patterns(turn: TurnParseResult):
        return [
            item
            for item in turn.disallowed_patterns
            if item.pattern_id.strip().lower()
            not in {
                "overlay_exclusion",
                "overlay_prohibition",
                "overlay_restriction",
                "no_overlay",
                "no_overlays",
            }
        ]
