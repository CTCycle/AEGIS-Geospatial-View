from __future__ import annotations

from typing import Any

from server.domain.agent.decision import (
    ClarificationRequest,
    DecisionTrace,
    ExecutionPlan,
    PolicyDecision,
)
from server.domain.agent.policies import (
    AgentPolicyConstraints,
    ToolAuthorizationResult,
    ToolValidationResult,
)
from server.domain.extraction.models import TurnParseResult
from server.services.geospatial.capability_registry import CapabilityRegistry
from server.services.geospatial.runtime_registry import RuntimeRegistry
from server.services.agent.location_resolver import LocationResolver


class PolicyEngine:
    def __init__(
        self,
        *,
        location_resolver: LocationResolver,
        capability_registry: CapabilityRegistry | None = None,
        runtime_registry: RuntimeRegistry | None = None,
        **_: Any,
    ) -> None:
        self.location_resolver = location_resolver
        self.capability_registry = capability_registry
        self.runtime_registry = runtime_registry

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

    def authorize_capability_execution(
        self,
        capability_id: str,
        arguments: dict[str, Any],
        parsed_request: TurnParseResult,
        context: Any,
    ) -> ToolAuthorizationResult:
        constraints = getattr(context, "policy_constraints", {}) or {}
        blocked_patterns = constraints.get("blocked_patterns")
        if blocked_patterns:
            return ToolAuthorizationResult(
                allowed=False,
                reason="Request contains blocked policy patterns.",
                metadata={"code": "tool_rejected"},
            )

        capability = (
            self.capability_registry.get_capability(capability_id)
            if self.capability_registry is not None
            else None
        )
        if capability is None:
            return ToolAuthorizationResult(
                allowed=False,
                reason=f"Unknown geospatial capability '{capability_id}'.",
                metadata={"code": "unsupported_capability"},
            )

        runtime_registry = self.runtime_registry
        if runtime_registry is None:
            return ToolAuthorizationResult(allowed=True)

        provider_health = runtime_registry.provider_health(capability_id)
        if provider_health == "disabled":
            return ToolAuthorizationResult(
                allowed=False,
                reason=f"Capability '{capability_id}' is disabled.",
                metadata={"code": "unsupported_capability", "provider_health": provider_health},
            )
        if provider_health == "missing_credentials":
            return ToolAuthorizationResult(
                allowed=False,
                reason=f"Capability '{capability_id}' requires provider credentials.",
                metadata={"code": "missing_credentials", "provider_health": provider_health},
            )

        requested_mode = self._requested_capability_mode(parsed_request)
        if requested_mode is not None and not runtime_registry.supports_mode(capability_id, requested_mode):
            return ToolAuthorizationResult(
                allowed=False,
                reason=(
                    f"Capability '{capability_id}' does not support the requested "
                    f"{'map' if requested_mode == 'map' else 'direct text'} mode."
                ),
                metadata={"code": "unsupported_capability", "requested_mode": requested_mode},
            )

        if self._requires_location_for_capability(parsed_request, capability) and not self._has_location_context(
            arguments=arguments,
            parsed_request=parsed_request,
        ):
            return ToolAuthorizationResult(
                allowed=False,
                reason="Location is required for this capability execution.",
                metadata={"code": "invalid_arguments", "missing_fields": ["location"]},
            )

        bbox = arguments.get("bbox")
        if bbox is not None and not self._is_sane_bbox(bbox):
            return ToolAuthorizationResult(
                allowed=False,
                reason="Bounding box must contain four numeric values in valid longitude/latitude ranges.",
                metadata={"code": "invalid_arguments", "field": "bbox"},
            )

        return ToolAuthorizationResult(allowed=True)

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
    def _requested_capability_mode(parsed_request: TurnParseResult) -> str | None:
        if parsed_request.task_class == "map_search":
            return "map"
        if parsed_request.task_class == "direct_query":
            return "direct_text"
        return None

    @staticmethod
    def _requires_location_for_capability(parsed_request: TurnParseResult, capability: dict[str, Any]) -> bool:
        if parsed_request.normalized_action.requires_location:
            return True
        geometry_type = str((capability.get("metadata") or {}).get("geometry_type") or "").strip().lower()
        return geometry_type not in {"", "not-applicable", "global"}

    @staticmethod
    def _has_location_context(
        *,
        arguments: dict[str, Any],
        parsed_request: TurnParseResult,
    ) -> bool:
        if any(key in arguments for key in ("location", "latitude", "longitude", "bbox")):
            return True
        if parsed_request.location_signals:
            return True
        active_location = parsed_request.conversation_context.memory_snapshot.get("active_location")
        return isinstance(active_location, dict) and bool(active_location.get("label"))

    @staticmethod
    def _is_sane_bbox(value: Any) -> bool:
        if not isinstance(value, list) or len(value) != 4:
            return False
        if not all(isinstance(item, (int, float)) for item in value):
            return False
        min_lon, min_lat, max_lon, max_lat = [float(item) for item in value]
        return (
            -180.0 <= min_lon <= 180.0
            and -180.0 <= max_lon <= 180.0
            and -90.0 <= min_lat <= 90.0
            and -90.0 <= max_lat <= 90.0
            and min_lon < max_lon
            and min_lat < max_lat
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
