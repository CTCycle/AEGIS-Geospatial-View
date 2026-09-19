"""Native turn coordination and the application response adapter."""

from __future__ import annotations

from collections.abc import Awaitable, Mapping
from dataclasses import dataclass, field
from typing import Any, Callable, Literal, cast

from server.contracts.chat import (
    ChatOperationResult,
    AgentToolResultSummary,
    AgentTurnResponse,
)
from server.contracts.geospatial import MapSession
from server.domain.agent.context import AgentContextPackage
from server.domain.agent.capability_route import AgentRunState
from server.domain.agent.decision import ResolvedLocation
from server.domain.agent.reliability import AgentExecutionBudget
from server.services.agent.agent_loop import AgentLoop, AgentLoopOutcome, AgentLoopRequest
from server.services.agent.agent_state_factory import AgentStateFactory

type PresentationStatus = Literal[
    "not_requested", "prepared", "prepared_unverified", "ready", "failed"
]
type FailureCategory = Literal[
    "model_capability",
    "provider_api",
    "provider_failure",
    "schema_definition",
    "response_parsing",
    "context_limit",
    "insufficient_evidence",
    "model_budget_exhausted",
    "tool_budget_exhausted",
    "transition_budget_exhausted",
    "iteration_budget_exhausted",
    "run_deadline_exhausted",
    "no_progress",
    "render_recovery_exhausted",
    "cancelled",
    "superseded",
]

###############################################################################
@dataclass(frozen=True)
class AgentTurnRequest:
    request_id: str
    conversation_id: str
    user_message: str
    provider: str
    model: str
    budget: AgentExecutionBudget
    messages: list[dict[str, Any]] = field(
        default_factory=lambda: list[dict[str, Any]]()
    )
    context_package: AgentContextPackage | None = None
    active_map_session: MapSession | None = None
    location_refs: Mapping[str, ResolvedLocation] = field(
        default_factory=lambda: dict[str, ResolvedLocation]()
    )
    evidence_refs: list[str] = field(default_factory=lambda: list[str]())
    run_version: int = 1
    conversation_revision: int = 0
    checkpoint: Mapping[str, Any] | None = None
    defer_map_commit: bool = False
    run_id: str | None = None
    context_usage_callback: Callable[[dict[str, Any]], None] | None = None
    trace_callback: Callable[[Any], Awaitable[None] | None] | None = None
    checkpoint_callback: Callable[[AgentRunState], Awaitable[None]] | None = None
    run_state_check: Callable[[], str | None] | None = None

###############################################################################
class AgentTurnRunner:
    """Run one typed native turn and build a bounded public result."""

    # -------------------------------------------------------------------------
    def __init__(self, *, agent_loop: AgentLoop, execution_settings: Any = None) -> None:
        self.agent_loop = agent_loop
        self.execution_settings = execution_settings

    # -------------------------------------------------------------------------
    async def run(self, request: AgentTurnRequest) -> AgentTurnResponse:
        if request.checkpoint is not None:
            state = AgentRunState.from_checkpoint(dict(request.checkpoint))
            if (
                state.request_id != request.request_id
                or state.conversation_id != request.conversation_id
            ):
                raise ValueError("Native run checkpoint belongs to another request.")
            state.user_message = request.user_message.strip()
            state.run_id = request.run_id
            state.run_version = request.run_version
            state.conversation_revision = request.conversation_revision
            state.termination_reason = None
            request.budget.restore_from_snapshot(state.budget_snapshot)
        else:
            state = AgentStateFactory.create(
                request_id=request.request_id,
                run_id=request.run_id,
                conversation_id=request.conversation_id,
                user_message=request.user_message,
                active_map_session=request.active_map_session,
                location_refs=request.location_refs,
                evidence_refs=request.evidence_refs,
                context_package=request.context_package,
                run_version=request.run_version,
                conversation_revision=request.conversation_revision,
            )
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
                    self.execution_settings, "complex_max_state_transitions", 64
                ),
                simple_max_model_calls=_setting(
                    self.execution_settings, "simple_max_model_calls", 4
                ),
                simple_max_tool_calls=_setting(
                    self.execution_settings, "simple_max_tool_calls", 6
                ),
                simple_max_state_transitions=_setting(
                    self.execution_settings, "simple_max_state_transitions", 32
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
                max_discovery_attempts=_setting(
                    self.execution_settings, "max_discovery_attempts", 2
                ),
                max_tool_result_chars=_setting(
                    self.execution_settings, "max_tool_result_chars", 4096
                ),
                max_no_progress_corrections=_setting(
                    self.execution_settings, "max_no_progress_corrections", 2
                ),
                max_render_attempts=_setting(
                    self.execution_settings, "max_render_attempts", 3
                ),
                context_usage_callback=request.context_usage_callback,
                trace_callback=request.trace_callback,
                checkpoint_callback=request.checkpoint_callback,
                run_state_check=request.run_state_check,
            )
        )
        return AgentResponseBuilder.build(
            request=request,
            outcome=outcome,
        )

###############################################################################
class AgentResponseBuilder:

    # -------------------------------------------------------------------------
    @staticmethod
    def build(
        *, request: AgentTurnRequest, outcome: AgentLoopOutcome
    ) -> AgentTurnResponse:
        state = outcome.state
        map_session = state.prepared_map_session
        message = outcome.final_text.strip() or _fallback_message(outcome)
        summaries = [
            AgentToolResultSummary(
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
        return AgentTurnResponse(
            request_id=request.request_id,
            conversation_id=request.conversation_id,
            assistant_message=message,
            route=state.route,
            goal=state.goal,
            completion_contract=state.completion_contract,
            task_state=state.typed_task_state(),
            operation=operation,
            map_session=map_session,
            presentation_status=_presentation_status(
                outcome,
                map_session,
                defer_map_commit=request.defer_map_commit,
            ),
            tool_results=summaries,
            execution_trace={
                "stopped_reason": outcome.stopped_reason,
                "model_calls": outcome.model_calls,
                "tool_calls": state.tool_calls,
                "transitions": state.transitions,
                "transition_trace": list(state.transition_trace[-64:]),
                "exposure_trace": list(state.exposure_trace[-64:]),
                "termination_reason": state.termination_reason,
                "budget": dict(state.budget_snapshot),
                "context_usage_trace": list(state.context_usage_trace[-16:]),
                "model_trace": list(state.model_trace[-16:]),
                "tool_trace": list(state.tool_trace[-32:]),
                "render_observations": [
                    item.model_dump(mode="json")
                    for item in state.render_observations[-8:]
                ],
                "render_attempts": state.render_attempts,
                "render_verified": state.render_verified,
                "task_state": state.typed_task_state().model_dump(
                    mode="json", exclude_none=True
                ),
                "checkpoint": state.checkpoint(),
            },
            location_refs=dict(state.location_refs),
        )

###############################################################################
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
        "provider_error",
        "context_limit",
        "model_budget_exhausted",
        "tool_budget_exhausted",
        "transition_budget_exhausted",
        "iteration_budget_exhausted",
        "run_deadline_exhausted",
        "no_progress",
        "render_recovery_exhausted",
        "cancelled",
        "superseded",
    }:
        return ChatOperationResult(
            kind="error",
            status="failed",
            message=message,
            failure_category=_response_failure_category(
                outcome.failure_category or outcome.stopped_reason
            ),
        )
    return ChatOperationResult(
        kind="direct_answer",
        status="success",
        message=message,
    )

###############################################################################
def _presentation_status(
    outcome: AgentLoopOutcome,
    map_session: MapSession | None,
    *,
    defer_map_commit: bool,
) -> PresentationStatus:
    route = outcome.state.route
    if route is None or route.presentation == "text":
        return "not_requested"
    if map_session is not None:
        return "prepared" if defer_map_commit else "prepared_unverified"
    if outcome.state.render_verified:
        return "ready"
    return "failed"

###############################################################################
def _fallback_message(outcome: AgentLoopOutcome) -> str:
    if outcome.failure_detail:
        return outcome.failure_detail
    if outcome.stopped_reason == "awaiting_render":
        return "A map candidate is prepared and awaiting render acknowledgment."
    if outcome.stopped_reason == "insufficient_evidence":
        return "I could not verify enough evidence to complete the request."
    return "The agent completed without a final response."

###############################################################################
def _response_failure_category(value: str | None) -> FailureCategory | None:
    if value == "provider_error":
        return "provider_failure"
    if value in {
        "model_capability",
        "provider_api",
        "provider_failure",
        "schema_definition",
        "response_parsing",
        "context_limit",
        "insufficient_evidence",
        "model_budget_exhausted",
        "tool_budget_exhausted",
        "transition_budget_exhausted",
        "iteration_budget_exhausted",
        "run_deadline_exhausted",
        "no_progress",
        "render_recovery_exhausted",
        "cancelled",
        "superseded",
    }:
        return cast(FailureCategory, value)
    return None

###############################################################################
def _setting(settings: Any, name: str, default: int | float) -> Any:
    value = getattr(settings, name, default) if settings is not None else default
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else default


__all__ = ["AgentResponseBuilder", "AgentTurnRequest", "AgentTurnRunner"]
