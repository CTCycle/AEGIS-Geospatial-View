"""Native-v2 turn coordination and the temporary response adapter."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from server.contracts.chat import (
    ChatOperationResult,
    NativeToolResultSummary,
    NativeV2TurnResponse,
)
from server.contracts.geospatial import MapSession
from server.domain.agent.decision import ResolvedLocation
from server.domain.agent.interpretation import CanonicalRequestInterpretation
from server.domain.agent.reliability import AgentExecutionBudget
from server.services.agent.agent_loop import AgentLoop, AgentLoopOutcome, AgentLoopRequest
from server.services.agent.agent_state_factory import AgentStateFactory


@dataclass(frozen=True)
class NativeV2TurnRequest:
    request_id: str
    conversation_id: str
    user_message: str
    provider: str
    model: str
    budget: AgentExecutionBudget
    messages: list[dict[str, Any]] = field(default_factory=list)
    active_map_session: MapSession | None = None
    location_refs: Mapping[str, ResolvedLocation] = field(default_factory=dict)
    evidence_refs: list[str] = field(default_factory=list)
    canonical_request: CanonicalRequestInterpretation | None = None
    defer_map_commit: bool = False
    run_id: str | None = None


class NativeV2TurnRunner:
    """Run one typed native turn and build a bounded public result."""

    def __init__(self, *, agent_loop: AgentLoop, execution_settings: Any = None) -> None:
        self.agent_loop = agent_loop
        self.execution_settings = execution_settings

    async def run(self, request: NativeV2TurnRequest) -> NativeV2TurnResponse:
        state = AgentStateFactory.create(
            request_id=request.request_id,
            run_id=request.run_id,
            conversation_id=request.conversation_id,
            user_message=request.user_message,
            active_map_session=request.active_map_session,
            location_refs=request.location_refs,
            evidence_refs=request.evidence_refs,
        )
        state.canonical_request = request.canonical_request
        outcome = await self.agent_loop.run(
            AgentLoopRequest(
                provider=request.provider,
                model=request.model,
                state=state,
                budget=request.budget,
                messages=list(request.messages),
                max_model_call_seconds=_setting(
                    self.execution_settings, "native_model_call_seconds", 60.0
                ),
                max_iterations=_setting(
                    self.execution_settings, "max_iterations", 12
                ),
                max_model_calls=_setting(
                    self.execution_settings, "complex_max_model_calls", 10
                ),
                max_tool_calls=_setting(
                    self.execution_settings, "complex_max_tool_calls", 20
                ),
                max_state_transitions=_setting(
                    self.execution_settings, "complex_max_state_transitions", 32
                ),
                max_parallel_tool_calls=_setting(
                    self.execution_settings, "max_parallel_tool_calls", 8
                ),
                max_consecutive_tool_failures=_setting(
                    self.execution_settings, "max_consecutive_tool_failures", 3
                ),
                max_same_failed_fingerprint=_setting(
                    self.execution_settings, "max_same_failed_fingerprint", 2
                ),
                max_route_corrections=_setting(
                    self.execution_settings, "max_route_corrections", 1
                ),
                max_validation_corrections=_setting(
                    self.execution_settings, "max_validation_corrections", 2
                ),
                max_tool_result_chars=_setting(
                    self.execution_settings, "max_tool_result_chars", 4096
                ),
            )
        )
        return NativeV2ResponseBuilder.build(
            request=request,
            outcome=outcome,
        )


class NativeV2ResponseBuilder:
    @staticmethod
    def build(
        *, request: NativeV2TurnRequest, outcome: AgentLoopOutcome
    ) -> NativeV2TurnResponse:
        state = outcome.state
        map_session = state.prepared_map_session
        message = outcome.final_text.strip() or _fallback_message(outcome)
        summaries = [
            NativeToolResultSummary(
                call_id=result.call_id,
                tool_name=result.tool_name,
                status=result.status,
                summary=result.summary,
                evidence_refs=list(result.evidence_refs),
                map_candidate_id=result.map_candidate_id,
                error=result.error,
            )
            for result in outcome.tool_results
        ]
        operation = _operation(outcome, map_session, message)
        return NativeV2TurnResponse(
            request_id=request.request_id,
            conversation_id=request.conversation_id,
            assistant_message=message,
            route=state.route,
            operation=operation,
            map_session=map_session,
            presentation_status=_presentation_status(
                outcome,
                map_session,
                defer_map_commit=request.defer_map_commit,
            ),
            tool_results=summaries,
            canonical_request=request.canonical_request,
            execution_trace={
                "stopped_reason": outcome.stopped_reason,
                "model_calls": outcome.model_calls,
                "tool_calls": state.tool_calls,
                "transitions": state.transitions,
                "transition_trace": list(state.transition_trace[-64:]),
                "exposure_trace": list(state.exposure_trace[-64:]),
                "termination_reason": state.termination_reason,
            },
        )


def _operation(
    outcome: AgentLoopOutcome,
    map_session: MapSession | None,
    message: str,
) -> ChatOperationResult:
    if map_session is not None:
        return ChatOperationResult(
            kind="map_session",
            status="pending",
            message=message,
            warnings=[
                result.summary
                for result in outcome.tool_results
                if result.status == "partial"
            ],
        )
    if outcome.stopped_reason == "clarification_required":
        return ChatOperationResult(
            kind="clarification",
            status="partial",
            message=message,
        )
    if outcome.failure_category is not None or outcome.stopped_reason in {
        "failed",
        "insufficient_evidence",
        "tool_budget_exhausted",
        "run_deadline_exhausted",
    }:
        return ChatOperationResult(
            kind="error",
            status="failed",
            message=message,
            failure_category=_response_failure_category(outcome.failure_category),
        )
    return ChatOperationResult(
        kind="direct_answer",
        status="success",
        message=message,
    )


def _presentation_status(
    outcome: AgentLoopOutcome,
    map_session: MapSession | None,
    *,
    defer_map_commit: bool,
) -> str:
    route = outcome.state.route
    if route is None or route.presentation == "text":
        return "not_requested"
    if map_session is not None:
        return "prepared" if defer_map_commit else "prepared_unverified"
    return "failed"


def _fallback_message(outcome: AgentLoopOutcome) -> str:
    if outcome.failure_detail:
        return outcome.failure_detail
    if outcome.stopped_reason == "awaiting_render":
        return "A map candidate is prepared and awaiting render acknowledgment."
    if outcome.stopped_reason == "insufficient_evidence":
        return "I could not verify enough evidence to complete the request."
    return "The agent completed without a final response."


def _response_failure_category(value: str | None) -> str | None:
    if value == "provider_error":
        return "provider_api"
    if value in {
        "model_capability",
        "provider_api",
        "schema_definition",
        "response_parsing",
        "context_limit",
    }:
        return value
    return None


def _setting(settings: Any, name: str, default: int | float) -> Any:
    value = getattr(settings, name, default) if settings is not None else default
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else default


__all__ = ["NativeV2ResponseBuilder", "NativeV2TurnRequest", "NativeV2TurnRunner"]
