"""Unified native state machine for bounded agent execution."""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import re
from collections.abc import Awaitable, Collection, Sequence
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any, Callable, Literal, Protocol
from urllib.parse import urlparse

from server.common.typing import is_json_array, is_json_object
from server.domain.agent.capability_route import (
    AgentGoal,
    AgentPhase,
    AgentRunState,
    AgentTask,
    AgentTaskState,
    CapabilityRoute,
    CompletionStatus,
    CompletionContract,
    CompletionRequirementKind,
    CompletionRequirement,
    LoopDecision,
    TaskStatus,
)
from server.domain.agent.context import AgentContextView
from server.domain.agent.capability_domains import CapabilityDomain
from server.domain.agent.reliability import (
    AgentExecutionBudget,
    ExecutionBudgetExceeded,
)
from server.domain.agent.trace import AgentTraceEvent
from server.domain.agent.tool_result import (
    ModelObservation,
    ToolExecutionError,
    ToolExecutionMetadata,
    ToolResult,
)
from server.domain.llm.types import LLMRequest, LLMResult, LLMToolCall, LLMToolDefinition
from server.prompts.agent import build_native_context_messages
from server.prompts.capability_route import build_capability_route_prompt
from server.services.agent.capability_router import (
    CapabilityRouter,
    build_location_map_fallback_route,
)
from server.services.agent.context_assembler import select_pair_safe_messages
from server.services.agent.tool_executor import ToolExecutor
from server.services.agent.tool_registry import ToolRegistry
from server.services.llm.context_budget import (
    compute_context_usage,
    merge_provider_context_usage,
)
from server.services.llm.errors import LLMProviderRequestError, LLMStructuredOutputError
from server.services.llm.request_deadline import REQUEST_DEADLINE_METADATA_KEY
from server.services.llm.transport import LLMTransportPolicy

###############################################################################
class AgentProvider(Protocol):

    # -------------------------------------------------------------------------
    async def achat(
        self,
        request: LLMRequest,
        *,
        tools: Sequence[LLMToolDefinition] | None = None,
        tool_choice: str | None = "auto",
        response_json_schema: dict[str, Any] | None = None,
    ) -> LLMResult: ...

###############################################################################
class AgentProviderFactory(Protocol):

    # -------------------------------------------------------------------------
    def get_provider(self, provider: str) -> AgentProvider: ...


###############################################################################
class AgentRunControlSignal(RuntimeError):
    """Internal stop signal for cancellation or version supersession."""

    # -------------------------------------------------------------------------
    def __init__(self, reason: Literal["cancelled", "superseded"]) -> None:
        self.reason = reason
        super().__init__(reason)

###############################################################################
@dataclass(frozen=True)
class AgentLoopRequest:
    provider: str
    model: str
    state: AgentRunState
    budget: AgentExecutionBudget
    messages: list[dict[str, Any]] = field(
        default_factory=lambda: list[dict[str, Any]]()
    )
    context_profile_metadata: dict[str, Any] = field(
        default_factory=lambda: dict[str, Any]()
    )
    temperature: float = 0.2
    max_model_call_seconds: float = 60.0
    max_iterations: int = 12
    max_model_calls: int = 10
    max_tool_calls: int = 20
    max_state_transitions: int = 64
    simple_max_model_calls: int = 4
    simple_max_tool_calls: int = 6
    simple_max_state_transitions: int = 32
    max_parallel_tool_calls: int = 8
    max_consecutive_tool_failures: int = 3
    max_same_failed_fingerprint: int = 2
    max_route_corrections: int = 1
    max_validation_corrections: int = 2
    max_discovery_attempts: int = 2
    max_tool_result_chars: int = 4096
    max_no_progress_corrections: int = 2
    max_render_attempts: int = 3
    context_usage_callback: Callable[[dict[str, Any]], None] | None = None
    checkpoint_callback: Callable[[AgentRunState], Awaitable[None]] | None = None
    trace_callback: Callable[
        [AgentTraceEvent], Awaitable[None] | None
    ] | None = None
    run_state_check: Callable[[], str | None] | None = None

###############################################################################
@dataclass(frozen=True)
class AgentLoopOutcome:
    final_text: str
    state: AgentRunState
    stopped_reason: Literal[
        "goal_satisfied",
        "awaiting_render",
        "clarification_required",
        "insufficient_evidence",
        "provider_error",
        "context_limit",
        "model_budget_exhausted",
        "tool_budget_exhausted",
        "transition_budget_exhausted",
        "run_deadline_exhausted",
        "iteration_budget_exhausted",
        "no_progress",
        "cancelled",
        "superseded",
        "failed",
        "render_recovery_exhausted",
    ]
    model_calls: int
    tool_results: list[ToolResult] = field(default_factory=lambda: list[ToolResult]())
    failure_category: str | None = None
    failure_detail: str | None = None


###############################################################################
class AgentLoop:
    """Own routing, progressive tool exposure, execution, and stopping."""

    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        provider_factory: AgentProviderFactory,
        capability_router: CapabilityRouter,
        tool_registry: ToolRegistry,
        tool_executor: ToolExecutor,
        transport_policy: LLMTransportPolicy | None = None,
    ) -> None:
        self.provider_factory = provider_factory
        self.capability_router = capability_router
        self.tool_registry = tool_registry
        self.tool_executor = tool_executor
        self.transport_policy = transport_policy or LLMTransportPolicy()

    # -------------------------------------------------------------------------
    async def run(self, request: AgentLoopRequest) -> AgentLoopOutcome:
        state = request.state
        provider = self.provider_factory.get_provider(request.provider)
        messages = self._initial_messages(request)
        final_text = ""
        state.max_iterations = max(1, min(100, int(request.max_iterations)))
        self._ensure_task_state(state, request.max_iterations)
        request.budget.configure_limits(
            max_model_calls=request.max_model_calls,
            max_tool_calls=request.max_tool_calls,
            max_state_transitions=request.max_state_transitions,
        )
        try:
            self._ensure_run_control(request)
            self._transition(state, AgentPhase.ROUTE_REQUEST, request.budget)
            route_result = (
                (None, "", state.route)
                if state.route is not None
                else await self._route(request, provider, messages)
            )
            if route_result[0] is not None:
                final_text, reason = route_result[0], route_result[1]
                state.termination_reason = reason
                return self._outcome(state, final_text, reason, request)
            route = route_result[2]
            if route is None:
                return self._failed(
                    state,
                    request,
                    "The request could not be routed to a supported capability.",
                    category="response_parsing",
                )
            state.route = route
            profile = self._budget_profile(route)
            request.budget.promote(profile)
            request.budget.configure_limits(
                max_model_calls=(
                    min(request.max_model_calls, request.simple_max_model_calls)
                    if profile == "simple"
                    else request.max_model_calls
                ),
                max_tool_calls=(
                    min(request.max_tool_calls, request.simple_max_tool_calls)
                    if profile == "simple"
                    else request.max_tool_calls
                ),
                max_state_transitions=(
                    min(
                        request.max_state_transitions,
                        request.simple_max_state_transitions,
                    )
                    if profile == "simple"
                    else request.max_state_transitions
                ),
            )
            self._compile_native_goal(state, route)
            self._sync_task_state(state)
            await self._checkpoint(request)

            if state.render_retry_exhausted:
                final_text = await self._finalize_iteration_exhaustion(
                    request,
                    provider,
                    messages,
                )
                state.termination_reason = "render_recovery_exhausted"
                await self._emit_trace(
                    request,
                    AgentTraceEvent(
                        kind="render_retry_exhausted",
                        run_id=state.run_id or state.request_id,
                        run_version=state.run_version,
                        sequence=self._trace_sequence(state),
                        iteration=max(1, state.current_iteration),
                        payload={
                            "attempts": state.render_attempts,
                            "max_attempts": request.max_render_attempts,
                            "last_observation": (
                                state.render_observations[-1].model_dump(mode="json")
                                if state.render_observations
                                else None
                            ),
                            "termination_reason": "render_recovery_exhausted",
                        },
                    ),
                )
                await self._emit_completion_decision(
                    request,
                    reason="render_recovery_exhausted",
                    status="terminal",
                )
                return self._outcome(
                    state,
                    final_text,
                    "render_recovery_exhausted",
                    request,
                )

            # A render can be acknowledged after the final ordinary
            # iteration.  It still gets the required tools-disabled response
            # synthesis; do not turn an otherwise verified map into an
            # iteration-budget failure merely because no decision slot
            # remains.
            if (
                state.render_verified
                and state.prepared_map_session is None
                and not self._pending_native_requirements(state)
            ):
                final_text = await self._finalize_verified_render(
                    request,
                    provider,
                    messages,
                )
                await self._emit_completion_decision(
                    request,
                    reason="goal_satisfied",
                    status="terminal",
                )
                state.termination_reason = "goal_satisfied"
                return self._outcome(state, final_text, "goal_satisfied", request)

            # A render acknowledgement resumes the same checkpoint.  Continue
            # from the next unconsumed iteration instead of resetting the
            # counter and silently extending the run budget.
            start_iteration = min(
                state.max_iterations,
                max(0, int(state.current_iteration)),
            )
            return await self._run_iterations(
                request,
                provider,
                messages,
                route,
                start_iteration,
            )
        except AgentRunControlSignal as exc:
            state.termination_reason = exc.reason
            return self._outcome(state, final_text, exc.reason, request)
        except asyncio.CancelledError:
            state.termination_reason = "cancelled"
            return self._outcome(state, final_text, "cancelled", request)
        except ExecutionBudgetExceeded as exc:
            return self._budget_outcome(state, request, exc.reason)
        except LLMProviderRequestError as exc:
            if exc.timeout_origin == "application_deadline":
                state.termination_reason = "run_deadline_exhausted"
                return self._outcome(
                    state,
                    final_text,
                    "run_deadline_exhausted",
                    request,
                )
            return self._failed(
                state,
                request,
                "The selected model could not complete this request.",
                category=exc.category,
            )
        except TimeoutError:
            state.termination_reason = "run_deadline_exhausted"
            return self._outcome(state, final_text, "run_deadline_exhausted", request)
        except LLMStructuredOutputError as exc:
            return self._failed(state, request, "The selected model could not complete this request.", category=exc.category)
        except Exception:
            return self._failed(state, request, "The agent stopped after an unexpected execution failure.", category="provider_error")

    # -------------------------------------------------------------------------
    async def _run_iterations(
        self,
        request: AgentLoopRequest,
        provider: AgentProvider,
        messages: list[dict[str, Any]],
        route: CapabilityRoute,
        start_iteration: int,
    ) -> AgentLoopOutcome:
        """Advance bounded model iterations until one terminal outcome exists."""

        state = request.state
        for iteration in range(start_iteration, state.max_iterations):
            outcome = await self._run_iteration(
                request,
                provider,
                messages,
                route,
                iteration,
            )
            if outcome is not None:
                return outcome
        final_text = await self._finalize_iteration_exhaustion(
            request,
            provider,
            messages,
        )
        return self._outcome(
            state,
            final_text,
            "iteration_budget_exhausted",
            request,
        )

    # -------------------------------------------------------------------------
    async def _run_iteration(
        self,
        request: AgentLoopRequest,
        provider: AgentProvider,
        messages: list[dict[str, Any]],
        route: CapabilityRoute,
        iteration: int,
    ) -> AgentLoopOutcome | None:
        """Run one model/tool/observation cycle and return only terminal work."""

        state = request.state
        self._ensure_run_control(request)
        state.current_iteration = iteration + 1
        state.iteration = state.current_iteration
        self._sync_task_state(state)
        iteration_started: dict[str, object] = {
            "iteration": state.current_iteration,
            "status": "started",
            "task_id": self._active_task_id(state),
        }
        state.iteration_trace.append(iteration_started)
        request.budget.record_iteration(iteration_started)
        await self._emit_trace(
            request,
            AgentTraceEvent(
                kind="iteration_started",
                run_id=state.run_id or state.request_id,
                run_version=state.run_version,
                sequence=self._trace_sequence(state),
                iteration=state.current_iteration,
                task_id=self._active_task_id(state),
                payload={"status": "started"},
            ),
        )
        model_limit = request.budget.max_model_calls or request.max_model_calls
        if state.model_calls >= model_limit:
            return self._budget_outcome(state, request, "model_budget_exhausted")
        self._transition(state, AgentPhase.BUILD_TOOL_CONTEXT, request.budget)
        tools = self.tool_registry.expose(state)
        exposed_tool_names = frozenset(item.name for item in tools)
        if not tools and route.task_mode == "execute" and not state.tool_results:
            return self._failed(
                state,
                request,
                "No actionable tool is available for this route.",
                category="model_capability",
            )
        self._transition(state, AgentPhase.MODEL_STEP, request.budget)
        result = await self._model_step(request, provider, messages, tools)
        if result.tool_calls:
            messages.extend(self._assistant_and_tool_messages(result))
            tool_results = await self._execute_calls(
                request,
                result.tool_calls,
                state,
                exposed_tool_names=exposed_tool_names,
            )
            location_map_recovery = await self._recover_location_only_map(
                request,
                route,
                state,
            )
            if location_map_recovery:
                # A successful location lookup is enough to complete a
                # location-only map contract.  Providers can otherwise keep
                # repeating the same lookup until the iteration budget is
                # exhausted instead of issuing the required map plan.
                tool_results.extend(location_map_recovery)
            self._ensure_run_control(request)
            messages.extend(
                self._tool_result_messages(
                    result.tool_calls,
                    tool_results,
                    max_chars=request.max_tool_result_chars,
                )
            )
            state.provider_continuation = [
                dict(item) for item in self._protocol_messages(messages)
            ]
            self._transition(state, AgentPhase.UPDATE_STATE, request.budget)
            self._sync_task_state(state)
            self._transition(state, AgentPhase.EVALUATE_STOP, request.budget)
            stop = self._evaluate_stop(
                state,
                route,
                tool_results,
                max_consecutive_tool_failures=request.max_consecutive_tool_failures,
                max_validation_corrections=request.max_validation_corrections,
                max_discovery_attempts=request.max_discovery_attempts,
            )
            await self._checkpoint(request)
            if (
                stop is None
                and state.context_hydrated
                and route.task_mode == "execute"
                and state.prepared_map_session is None
                and bool(state.completion_requirements)
                and not self._pending_native_requirements(state)
            ):
                final_text = await self._finalize_completed_request(
                    request, provider, messages
                )
                await self._emit_completion_decision(
                    request, reason="goal_satisfied", status="terminal"
                )
                state.termination_reason = "goal_satisfied"
                return self._outcome(state, final_text, "goal_satisfied", request)
            if stop is not None:
                if await self._continue_after_no_progress(request, messages, stop):
                    return None
                await self._emit_completion_decision(
                    request, reason=stop[0], status="terminal"
                )
                state.termination_reason = stop[0]
                return self._outcome(state, stop[1], stop[0], request)
            await self._emit_iteration_completed(request, "continue")
            if iteration + 1 >= state.max_iterations:
                final_text = await self._finalize_iteration_exhaustion(
                    request, provider, messages
                )
                return self._outcome(
                    state, final_text, "iteration_budget_exhausted", request
                )
            return None

        final_text = result.content.strip()
        recovery_results = await self._recover_location_only_map(request, route, state)
        self._transition(state, AgentPhase.EVALUATE_STOP, request.budget)
        stop = (
            self._evaluate_stop(
                state,
                route,
                recovery_results,
                max_consecutive_tool_failures=request.max_consecutive_tool_failures,
                max_validation_corrections=request.max_validation_corrections,
                max_discovery_attempts=request.max_discovery_attempts,
            )
            if recovery_results
            else self._evaluate_text_stop(
                state,
                route,
                final_text,
                available_tools=[item.name for item in tools],
            )
        )
        if recovery_results and any(
            item.tool_name == "apply_map_plan" and item.status == "success"
            for item in recovery_results
        ):
            final_text = "The map is ready."
        self._sync_task_state(state)
        await self._checkpoint(request)
        if stop is not None:
            if await self._continue_after_no_progress(request, messages, stop):
                return None
            await self._emit_completion_decision(
                request, reason=stop[0], status="terminal"
            )
            state.termination_reason = stop[0]
            return self._outcome(state, final_text, stop[0], request)
        messages.append({"role": "assistant", "content": final_text})
        await self._emit_iteration_completed(request, "continue")
        if iteration + 1 >= state.max_iterations:
            final_text = await self._finalize_iteration_exhaustion(
                request, provider, messages
            )
            return self._outcome(
                state, final_text, "iteration_budget_exhausted", request
            )
        return None

    # -------------------------------------------------------------------------
    async def _continue_after_no_progress(
        self,
        request: AgentLoopRequest,
        messages: list[dict[str, Any]],
        stop: tuple[str, str],
    ) -> bool:
        state = request.state
        if (
            stop[0] != "no_progress"
            or state.no_progress_corrections >= request.max_no_progress_corrections
        ):
            return False
        state.no_progress_corrections += 1
        correction = self._no_progress_correction(state)
        state.relevant_tool_outcomes.append(correction)
        messages.append(
            {
                "role": "system",
                "content": json.dumps(correction, separators=(",", ":")),
            }
        )
        await self._emit_completion_decision(
            request, reason="no_progress", status="continue"
        )
        await self._emit_iteration_completed(request, "continue")
        return True

    # -------------------------------------------------------------------------
    async def _emit_trace(
        self,
        request: AgentLoopRequest,
        event: AgentTraceEvent,
    ) -> None:
        """Deliver one operational event to the durable run sink, if wired."""

        callback = request.trace_callback
        if callback is None:
            return
        result = callback(event)
        if inspect.isawaitable(result):
            await result

    # -------------------------------------------------------------------------
    async def _emit_iteration_completed(
        self,
        request: AgentLoopRequest,
        status: Literal["continue", "exhausted"],
    ) -> None:
        state = request.state
        record: dict[str, object] = {
            "iteration": state.current_iteration,
            "status": status,
            "task_id": self._active_task_id(state),
        }
        state.iteration_trace.append(record)
        request.budget.record_iteration(record)
        await self._emit_trace(
            request,
            AgentTraceEvent(
                kind="iteration_completed",
                run_id=state.run_id or state.request_id,
                run_version=state.run_version,
                sequence=self._trace_sequence(state),
                iteration=max(1, state.current_iteration),
                task_id=self._active_task_id(state),
                payload={"status": status},
            ),
        )

    # -------------------------------------------------------------------------
    async def _emit_completion_decision(
        self,
        request: AgentLoopRequest,
        *,
        reason: str,
        status: Literal["continue", "terminal"],
    ) -> None:
        """Record a bounded completion decision without model reasoning."""

        state = request.state
        decision = self._loop_decision(reason, status)
        await self._emit_trace(
            request,
            AgentTraceEvent(
                kind="completion_decision",
                run_id=state.run_id or state.request_id,
                run_version=state.run_version,
                sequence=self._trace_sequence(state),
                iteration=max(1, state.current_iteration),
                payload={
                    "decision": decision.value,
                    "status": status,
                    "reason": reason,
                    "pending_requirements": self._pending_native_requirements(state),
                    "render_verified": state.render_verified,
                    "render_attempts": state.render_attempts,
                },
            ),
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def _loop_decision(
        reason: str,
        status: Literal["continue", "terminal"],
    ) -> LoopDecision:
        if status == "continue":
            return LoopDecision.CONTINUE
        if reason == "clarification_required":
            return LoopDecision.REQUEST_CLARIFICATION
        if reason == "awaiting_render":
            return LoopDecision.AWAIT_RENDER
        if reason == "cancelled":
            return LoopDecision.CANCEL
        if reason == "superseded":
            return LoopDecision.SUPERSEDE
        if reason == "goal_satisfied":
            return LoopDecision.COMPLETE
        return LoopDecision.FAIL

    # -------------------------------------------------------------------------
    async def _finalize_iteration_exhaustion(
        self,
        request: AgentLoopRequest,
        provider: AgentProvider,
        messages: list[dict[str, Any]],
    ) -> str:
        """Make one bounded, tools-disabled finalization attempt.

        Exhaustion is a distinct terminal state even when the provider can
        provide a useful final explanation.  The model is never allowed to
        issue another tool call during this finalization step; unresolved
        server-owned obligations are appended deterministically so a polished
        but unsupported claim cannot be mistaken for completion.
        """

        state = request.state
        candidate = ""
        model_limit = request.budget.max_model_calls or request.max_model_calls
        can_finalize = (
            not state.finalization_attempted
            and state.model_calls < model_limit
            and request.budget.remaining_seconds() > 0.001
        )
        finalization_reason = "iteration_exhaustion"
        if can_finalize:
            state.finalization_attempted = True
            await self._emit_finalization_trace(
                request,
                reason=finalization_reason,
                kind="finalization_started",
            )
            outcome = "empty"
            try:
                result = await self._model_step(request, provider, messages, [])
                # A provider violating ``tools=[]`` is treated as an empty
                # finalization result; the deterministic explanation remains
                # the safe terminal response.
                if not result.tool_calls:
                    candidate = (result.content or "").strip()
                    outcome = "text" if candidate else "empty"
                else:
                    outcome = "tool_calls_suppressed"
            except (AgentRunControlSignal, asyncio.CancelledError):
                outcome = "cancelled"
                raise
            except (
                ExecutionBudgetExceeded,
                LLMProviderRequestError,
                LLMStructuredOutputError,
                TimeoutError,
            ):
                outcome = "provider_error"
                candidate = ""
            except Exception:
                outcome = "error"
                candidate = ""
            finally:
                await self._emit_finalization_trace(
                    request,
                    reason=finalization_reason,
                    kind="finalization_completed",
                    outcome=outcome,
                )
        else:
            await self._emit_finalization_trace(
                request,
                reason=finalization_reason,
                kind="finalization_completed",
                outcome=(
                    "already_attempted"
                    if state.finalization_attempted
                    else "budget_unavailable"
                ),
            )

        pending = self._pending_requirements_for_task_state(state)
        if state.render_retry_exhausted:
            suffix = (
                "The map renderer did not produce a verified result after "
                f"{state.render_attempts} attempt(s); the previous map remains "
                "available."
            )
        elif pending:
            suffix = (
                "The iteration limit was reached before these requirements were "
                "satisfied: "
                + ", ".join(item.replace("_", " ") for item in pending)
                + "."
            )
        else:
            suffix = (
                "The iteration limit was reached before completion could be "
                "verified."
            )
        final = candidate.rstrip()
        if final:
            final = f"{final}\n\n{suffix}"
        else:
            final = suffix
        await self._emit_iteration_completed(request, "exhausted")
        return final

    # -------------------------------------------------------------------------
    async def _finalize_verified_render(
        self,
        request: AgentLoopRequest,
        provider: AgentProvider,
        messages: list[dict[str, Any]],
    ) -> str:
        """Synthesize the final answer after a verified browser render."""

        state = request.state
        candidate = ""
        model_limit = request.budget.max_model_calls or request.max_model_calls
        if (
            not state.finalization_attempted
            and state.model_calls < model_limit
            and request.budget.remaining_seconds() > 0.001
        ):
            state.finalization_attempted = True
            finalization_reason = "verified_render"
            await self._emit_finalization_trace(
                request,
                reason=finalization_reason,
                kind="finalization_started",
            )
            outcome = "empty"
            try:
                result = await self._model_step(request, provider, messages, [])
                if not result.tool_calls:
                    candidate = (result.content or "").strip()
                    outcome = "text" if candidate else "empty"
                else:
                    outcome = "tool_calls_suppressed"
            except (AgentRunControlSignal, asyncio.CancelledError):
                outcome = "cancelled"
                raise
            except (
                ExecutionBudgetExceeded,
                LLMProviderRequestError,
                LLMStructuredOutputError,
                TimeoutError,
            ):
                outcome = "provider_error"
                candidate = ""
            except Exception:
                outcome = "error"
                candidate = ""
            finally:
                await self._emit_finalization_trace(
                    request,
                    reason=finalization_reason,
                    kind="finalization_completed",
                    outcome=outcome,
                )
        else:
            await self._emit_finalization_trace(
                request,
                reason="verified_render",
                kind="finalization_completed",
                outcome=(
                    "already_attempted"
                    if state.finalization_attempted
                    else "budget_unavailable"
                ),
            )
        verified_map_state = self._verified_map_state_summary(state)
        if verified_map_state is not None:
            return verified_map_state
        return candidate or "The map is ready and the rendering was verified."

    # -------------------------------------------------------------------------
    @staticmethod
    def _verified_map_state_summary(state: AgentRunState) -> str | None:
        """Ground map-lifecycle narration in the committed browser state."""

        route = state.route
        session = state.active_map_session
        if (
            route is None
            or route.primary_domain is not CapabilityDomain.MAP_STATE
            or session is None
        ):
            return None

        basemap = session.basemap or {}
        basemap_label = str(
            basemap.get("label") or basemap.get("name") or session.basemap_id
        ).strip()
        visible = [
            str(instance.label or instance.capability_id).strip()
            for instance in session.overlay_collection.instances
            if instance.visible
        ]
        hidden = [
            str(instance.label or instance.capability_id).strip()
            for instance in session.overlay_collection.instances
            if not instance.visible
        ]
        visible_text = ", ".join(item for item in visible if item) or "none"
        summary = (
            "Map state update verified in the browser. "
            f"Basemap: {basemap_label}. Visible overlays: {visible_text}."
        )
        if hidden:
            hidden_text = ", ".join(item for item in hidden if item)
            if hidden_text:
                summary += f" Hidden retained overlays: {hidden_text}."
        return summary

    # -------------------------------------------------------------------------
    async def _finalize_completed_request(
        self,
        request: AgentLoopRequest,
        provider: AgentProvider,
        messages: list[dict[str, Any]],
    ) -> str:
        """Synthesize a completed non-render request with tools disabled."""

        state = request.state
        candidate = ""
        model_limit = request.budget.max_model_calls or request.max_model_calls
        reason = "goal_satisfied"
        if (
            not state.finalization_attempted
            and state.model_calls < model_limit
            and request.budget.remaining_seconds() > 0.001
        ):
            state.finalization_attempted = True
            await self._emit_finalization_trace(
                request, reason=reason, kind="finalization_started"
            )
            outcome = "empty"
            try:
                result = await self._model_step(request, provider, messages, [])
                if not result.tool_calls:
                    candidate = (result.content or "").strip()
                    outcome = "text" if candidate else "empty"
                else:
                    outcome = "tool_calls_suppressed"
            except (AgentRunControlSignal, asyncio.CancelledError):
                outcome = "cancelled"
                raise
            except (
                ExecutionBudgetExceeded,
                LLMProviderRequestError,
                LLMStructuredOutputError,
                TimeoutError,
            ):
                outcome = "provider_error"
            except Exception:
                outcome = "error"
            finally:
                await self._emit_finalization_trace(
                    request,
                    reason=reason,
                    kind="finalization_completed",
                    outcome=outcome,
                )
        return (
            candidate
            or self._completed_request_fallback(state)
            or "The requested information is ready."
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def _completed_request_fallback(state: AgentRunState) -> str:
        """Render a bounded direct answer when no final model slot remains."""

        for result in reversed(state.tool_results):
            if result.status not in {"success", "partial"}:
                continue
            data = result.data if is_json_object(result.data) else None
            if data is None or data.get("capability_id") != "get_weather_forecast":
                continue
            observations = data.get("observations")
            if not is_json_object(observations) or not observations:
                continue
            query = data.get("query")
            resolved_location = (
                query.get("resolved_location")
                if is_json_object(query)
                else None
            )
            location = str(
                resolved_location
                or (query.get("location_ref") if is_json_object(query) else None)
                or "the requested location"
            )
            fields = (
                ("temperature_2m", "temperature", "°C"),
                ("relative_humidity_2m", "humidity", "%"),
                ("precipitation", "precipitation", "mm"),
                ("wind_speed_10m", "wind", "km/h"),
                ("surface_pressure", "pressure", "hPa"),
            )
            values = [
                f"{label} {observations[key]}{unit}"
                for key, label, unit in fields
                if observations.get(key) is not None
            ]
            weather_code = observations.get("weather_code")
            if weather_code is not None:
                values.append(f"WMO weather code {weather_code}")
            if not values:
                continue
            answer = f"Current weather for {location}: " + "; ".join(values) + "."
            observation_time = data.get("observation_time")
            timezone = data.get("timezone")
            if observation_time:
                suffix = f"Observation time: {observation_time}"
                if timezone:
                    suffix += f" ({timezone})"
                answer += f" {suffix}."
            if result.status == "partial" or data.get("partial"):
                answer += " The provider marked this result as partial."
            return answer
        return ""

    # -------------------------------------------------------------------------
    async def _emit_finalization_trace(
        self,
        request: AgentLoopRequest,
        *,
        reason: str,
        kind: Literal["finalization_started", "finalization_completed"],
        outcome: str | None = None,
    ) -> None:
        """Expose the tools-disabled finalization boundary without content."""

        state = request.state
        payload: dict[str, Any] = {
            "reason": reason,
            "tools_exposed": 0,
            "tool_choice": "none",
            "model_call_index": state.model_calls,
        }
        if outcome is not None:
            payload["outcome"] = outcome
        await self._emit_trace(
            request,
            AgentTraceEvent(
                kind=kind,
                run_id=state.run_id or state.request_id,
                run_version=state.run_version,
                sequence=self._trace_sequence(state),
                iteration=max(1, state.current_iteration),
                payload=payload,
            ),
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def _trace_sequence(state: AgentRunState) -> int:
        return max(
            1,
            len(state.transition_trace)
            + len(state.iteration_trace)
            + len(state.tool_trace)
            + len(state.model_trace),
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def _active_task_id(state: AgentRunState) -> str | None:
        raw = state.task_state
        for key in ("active_task_id", "current_task_id", "root_task_id"):
            value = raw.get(key)
            if value is not None and str(value).strip():
                return str(value)
        return None

    # -------------------------------------------------------------------------
    @staticmethod
    def _ensure_task_state(state: AgentRunState, max_iterations: int) -> None:
        """Ensure every run has a deterministic root task in its state."""

        raw = dict(state.task_state)
        typed = AgentTaskState.from_payload(
            raw,
            run_id=state.run_id or state.request_id,
            description=state.user_message,
            max_iterations=max_iterations,
        )
        typed = typed.model_copy(
            update={
                "current_iteration": max(0, state.current_iteration),
                "max_iterations": max(1, min(100, int(max_iterations))),
            }
        )
        raw.update(typed.to_payload())
        state.task_state = raw

    # -------------------------------------------------------------------------
    @staticmethod
    def _initialize_task_state_for_route(
        state: AgentRunState,
        route: CapabilityRoute,
    ) -> None:
        requirements = list(state.completion_requirements)
        target_ids = list(state.goal.target_ids) if state.goal is not None else []
        compound = bool(
            len(requirements) > 1
            or len(target_ids) > 1
            or route.secondary_domains
            or len(route.capability_queries) > 1
        )
        raw = dict(state.task_state)
        typed = AgentTaskState.create(
            run_id=state.run_id or state.request_id,
            description=state.user_message,
            max_iterations=state.max_iterations,
            requirements=requirements,
            target_ids=target_ids,
            compound=compound,
        )
        # Preserve conversation-state keys from pre-hydrated checkpoints while
        # making the task ledger authoritative for its own namespace.
        raw.update(typed.to_payload())
        state.task_state = raw

    # -------------------------------------------------------------------------
    @staticmethod
    def _pending_requirements_for_task_state(state: AgentRunState) -> list[str]:
        checks = AgentLoop._completion_checks(state)
        contract = state.completion_contract
        if contract is None:
            return []
        required = list(contract.requirements)
        if contract.temporal_scope_required and "temporal_scope_applied" not in required:
            required.append("temporal_scope_applied")
        if contract.spatial_scope_required and "spatial_scope_applied" not in required:
            required.append("spatial_scope_applied")
        return [name for name in required if not checks.get(name, False)]

    # -------------------------------------------------------------------------
    @staticmethod
    def _completion_checks(state: AgentRunState) -> dict[str, bool]:
        completed_data = any(
            (
                result.status in {"success", "partial"}
                or (
                    result.status == "valid_empty"
                    and result.semantic_outcome != "not_found"
                )
            )
            and result.tool_name
            in {
                "execute_geospatial_capability",
                "inspect_evidence",
                "transform_evidence",
            }
            and (
                not state.capability_ids
                or result.metadata.capability_id in state.capability_ids
            )
            for result in state.tool_results
        )
        geocode_location_resolved = (
            state.route is not None
            and state.route.task_mode == "execute"
            and state.route.primary_domain is CapabilityDomain.PLACE_SEARCH
            and state.route.presentation == "text"
            and state.route.operation == "geocode"
            and bool(state.location_refs)
            and any(
                result.tool_name == "resolve_geospatial_location"
                and result.status == "success"
                for result in state.tool_results
            )
        )
        data_completed = completed_data or geocode_location_resolved
        return {
            "location_resolved": bool(state.location_refs)
            or state.active_map_session is not None,
            "required_data_retrieved": data_completed,
            "temporal_scope_applied": completed_data,
            # A successful map-plan observation is the server-owned proof
            # that the requested spatial scope was applied.  Location-only
            # map requests have no data tool result, so using ``completed_data``
            # alone left their spatial task pending even after a valid
            # candidate had been prepared.
            "spatial_scope_applied": data_completed
            or state.prepared_map_session is not None
            or (state.active_map_session is not None and state.render_verified),
            "map_candidate_prepared": state.prepared_map_session is not None
            or (state.active_map_session is not None and state.render_verified),
            "render_verified": bool(state.render_verified),
        }

    # -------------------------------------------------------------------------
    @staticmethod
    def _sync_task_state(state: AgentRunState) -> None:
        """Derive task statuses solely from completion obligations/results."""

        raw = dict(state.task_state)
        typed = AgentTaskState.from_payload(
            raw,
            run_id=state.run_id or state.request_id,
            description=state.user_message,
            max_iterations=state.max_iterations,
        )
        checks = AgentLoop._completion_checks(state)
        names = list(state.completion_requirements)
        requirements: list[CompletionRequirement] = []
        requirement_kinds: dict[str, CompletionRequirementKind] = {
            "location_resolved": "location",
            "required_data_retrieved": "provider_data",
            "temporal_scope_applied": "temporal_scope",
            "spatial_scope_applied": "spatial_scope",
            "map_candidate_prepared": "map_candidate",
            "render_verified": "render_ack",
        }
        existing = {
            item.name: item for item in typed.completion_requirements
        }
        for name in names:
            prior = existing.get(name)
            status: CompletionStatus
            if checks.get(name, False):
                status = "satisfied"
                failure_code = None
            else:
                status = prior.status if prior is not None else "pending"
                failure_code = prior.failure_code if prior is not None else None
                if status == "satisfied":
                    status = "pending"
            requirements.append(
                CompletionRequirement(
                    name=name,
                    kind=requirement_kinds.get(name),
                    required=True,
                    status=status,
                    target_id=prior.target_id if prior is not None else None,
                    evidence_ref=prior.evidence_ref if prior is not None else None,
                    failure_code=failure_code,
                )
            )

        pending_names = [
            item.name for item in requirements if item.status == "pending"
        ]
        pending = set(pending_names)
        failed = {
            item.name for item in requirements if item.status == "failed"
        }
        completed_targets = set(state.location_refs)
        for result in state.tool_results:
            if result.status not in {"success", "valid_empty", "partial"}:
                continue
            if isinstance(result.data, dict):
                target = result.data.get("target_id") or result.data.get("targetId")
                if target is not None and str(target).strip():
                    completed_targets.add(str(target).strip())
        updated_tasks: list[AgentTask] = []
        first_pending = pending_names[0] if pending_names else None
        target_pending = next(
            (
                task.target_id
                for task in typed.tasks
                if task.target_id and task.target_id not in completed_targets
            ),
            None,
        )
        for task in typed.tasks:
            update: dict[str, Any] = {}
            if task.task_id == typed.root_task_id:
                if failed:
                    update["status"] = "failed"
                elif not pending and requirements:
                    update["status"] = "completed"
                else:
                    update["status"] = "in_progress"
            elif task.requirement_name:
                if task.requirement_name not in names:
                    update["status"] = "blocked"
                elif task.requirement_name in failed:
                    update["status"] = "failed"
                elif task.requirement_name not in pending:
                    update["status"] = "completed"
                elif task.requirement_name == first_pending:
                    update["status"] = "in_progress"
                else:
                    update["status"] = "pending"
            elif task.target_id:
                if task.target_id in completed_targets:
                    update["status"] = "completed"
                elif task.target_id == target_pending:
                    update["status"] = "in_progress"
                else:
                    update["status"] = "pending"
            updated_tasks.append(task.model_copy(update=update))
        active = next(
            (
                task.task_id
                for task in updated_tasks
                if task.status == "in_progress" and task.task_id != typed.root_task_id
            ),
            typed.root_task_id,
        )
        ledger_status: TaskStatus = (
            "failed"
            if failed
            else "completed"
            if requirements and not pending
            else "in_progress"
        )
        typed = typed.model_copy(
            update={
                "active_task_id": active,
                "status": ledger_status,
                "current_iteration": max(0, state.current_iteration),
                "max_iterations": state.max_iterations,
                "tasks": updated_tasks,
                "completion_requirements": requirements,
            }
        )
        raw.update(typed.to_payload())
        state.task_state = raw

    # -------------------------------------------------------------------------
    @staticmethod
    def _set_terminal_task_state(state: AgentRunState, reason: str) -> None:
        raw = dict(state.task_state)
        typed = AgentTaskState.from_payload(
            raw,
            run_id=state.run_id or state.request_id,
            description=state.user_message,
            max_iterations=state.max_iterations,
        )
        status: TaskStatus = (
            "completed"
            if reason == "goal_satisfied"
            else "cancelled"
            if reason == "cancelled"
            else "superseded"
            if reason == "superseded"
            else "in_progress"
            if reason == "awaiting_render"
            else "blocked"
            if reason in {
                "iteration_budget_exhausted",
                "model_budget_exhausted",
                "tool_budget_exhausted",
                "transition_budget_exhausted",
                "run_deadline_exhausted",
                "no_progress",
                "render_recovery_exhausted",
                "clarification_required",
            }
            else "failed"
        )
        tasks = [
            task.model_copy(
                update={
                    "status": (
                        status
                        if task.task_id == typed.root_task_id
                        else task.status
                        if status == "in_progress"
                        else status
                    )
                }
            )
            for task in typed.tasks
        ]
        typed = typed.model_copy(update={"status": status, "tasks": tasks})
        raw.update(typed.to_payload())
        state.task_state = raw

    # -------------------------------------------------------------------------
    async def _route(
        self,
        request: AgentLoopRequest,
        provider: AgentProvider,
        messages: list[dict[str, Any]],
    ) -> tuple[str | None, str, CapabilityRoute | None]:
        registered_route_tool = self.tool_registry.get("route_request")
        if registered_route_tool is None:
            return "Routing is unavailable for this request.", "provider_error", None
        route_tool = registered_route_tool.definition
        correction_messages = [
            {"role": "system", "content": build_capability_route_prompt()},
            *messages,
        ]
        for attempt in range(request.max_route_corrections + 1):
            result = await self._model_call(
                request,
                provider,
                correction_messages,
                [route_tool],
                tool_choice="required",
                budget_stage="route_request",
            )
            call = result.tool_calls[0] if result.tool_calls else None
            if (
                call is not None
                and call.name == route_tool.name
                and call.parse_error is None
                and call.arguments is not None
            ):
                try:
                    proposed = CapabilityRoute.model_validate(call.arguments)
                except Exception:
                    proposed = None
                if proposed is not None:
                    decision = self.capability_router.validate_route(
                        proposed,
                        user_message=request.state.user_message,
                        active_state=request.state,
                    )
                    if decision.status in {"accepted", "discovery_required"}:
                        request.state.capability_ids = list(decision.capability_ids)
                        return None, "", decision.route
                    if decision.status == "clarification":
                        return (
                            decision.clarification_question
                            or "Which supported capability should I use?",
                            "clarification_required",
                            None,
                        )
                    if decision.status == "no_capability":
                        return (
                            "I could not find an enabled, available capability for that request.",
                            "insufficient_evidence",
                            None,
                        )
                    if decision.status == "rejected":
                        correction_messages.append(
                            {
                                "role": "user",
                                "content": json.dumps(
                                    {
                                        "route_rejected": True,
                                        "reason_codes": decision.reason_codes,
                                        "instruction": (
                                            "Return a corrected route_request call "
                                            "with no execution fields for answer or "
                                            "clarify task modes."
                                        ),
                                    },
                                    separators=(",", ":"),
                                ),
                            }
                        )
                        request.state.route_corrections = attempt + 1
                        continue
            request.state.route_corrections = attempt + 1
            correction_messages.append(
                {
                    "role": "user",
                    "content": "Return one valid route_request call matching the supplied schema.",
                }
            )
        fallback = build_location_map_fallback_route(request.state.user_message)
        if fallback is not None:
            decision = self.capability_router.validate_route(
                fallback,
                user_message=request.state.user_message,
                active_state=request.state,
            )
            if decision.status in {"accepted", "discovery_required"}:
                request.state.capability_ids = list(decision.capability_ids)
                return None, "", decision.route
        return None, "", None

    # -------------------------------------------------------------------------
    async def _model_step(
        self,
        request: AgentLoopRequest,
        provider: AgentProvider,
        messages: list[dict[str, Any]],
        tools: list[LLMToolDefinition],
    ) -> LLMResult:
        working = self._working_state_message(request.state, request.max_tool_result_chars)
        model_messages = [
            *self._model_context_messages(request, messages),
            {"role": "system", "content": working},
        ]
        return await self._model_call(
            request,
            provider,
            model_messages,
            tools,
            tool_choice="auto" if tools else "none",
        )

    # -------------------------------------------------------------------------
    def _model_context_messages(
        self,
        request: AgentLoopRequest,
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Rebuild semantic context while retaining provider protocol state."""

        state = request.state
        if not state.context_hydrated:
            return list(messages)
        observations = [
            ModelObservation.from_tool_result(
                result,
                max_chars=min(request.max_tool_result_chars, 2048),
            ).model_dump(mode="json", exclude_none=True)
            for result in state.tool_results[-8:]
        ]
        view = AgentContextView.from_state(
            state,
            recent_observations=observations,
            render_observations=[
                item.model_dump(mode="json")
                for item in state.render_observations[-8:]
            ],
        )
        context = build_native_context_messages(
            current_user_message=state.user_message,
            recent_messages=state.recent_messages,
            active_directives=view.active_directives,
            task_state=view.task_state,
            map_memory=view.map_memory,
            summary=view.summary,
            relevant_tool_outcomes=view.relevant_tool_outcomes,
            recent_observations=view.recent_observations,
            render_observations=view.render_observations,
            policy_constraints=view.policy_constraints,
            context_selection=view.context_selection,
        )
        protocol_messages = self._protocol_messages(messages)
        if not protocol_messages and state.provider_continuation:
            protocol_messages = self._protocol_messages(
                [dict(item) for item in state.provider_continuation]
            )
        return [*context, *protocol_messages]

    # -------------------------------------------------------------------------
    @staticmethod
    def _protocol_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        protocol = [
            message
            for message in messages
            if (
                str(message.get("type") or "")
                in {"message", "reasoning", "function_call", "function_call_output"}
                or (
                    message.get("role") == "assistant"
                    and message.get("tool_calls")
                )
                or message.get("role") == "tool"
            )
        ]
        # The canonical native context carries durable semantic history.  Keep
        # only the latest provider protocol window here so Responses reasoning
        # and function-call items remain paired without pinning every historical
        # tool exchange forever.
        return select_pair_safe_messages(protocol, max_items=16)

    # -------------------------------------------------------------------------
    async def _model_call(
        self,
        request: AgentLoopRequest,
        provider: AgentProvider,
        messages: list[dict[str, Any]],
        tools: list[LLMToolDefinition],
        *,
        tool_choice: str,
        budget_stage: str = "model_step",
    ) -> LLMResult:
        self._ensure_run_control(request)
        request.budget.ensure_available(budget_stage)
        metadata: dict[str, Any] = {
            "supports_tools": True,
            REQUEST_DEADLINE_METADATA_KEY: request.budget.deadline_monotonic,
        }
        protocol = self._provider_protocol(provider, request.model)
        endpoint_host = self._provider_endpoint_host(provider)
        metadata["protocol"] = protocol
        if endpoint_host is not None:
            metadata["endpoint_host"] = endpoint_host
        if request.provider == "opencode-go":
            # OpenCode Go's thinking-mode models reject explicit tool_choice
            # values while tools are enabled.  Disabling thinking selects the
            # provider's compatible native-tool contract without changing the
            # configured provider or model.
            metadata["thinking_mode"] = "disabled"
        profile_metadata = dict(request.context_profile_metadata)
        if (
            profile_metadata.get("context_profile_provider") == request.provider
            and profile_metadata.get("context_profile_model") == request.model
        ):
            metadata.update(profile_metadata)
        llm_request = LLMRequest(
            model=request.model,
            provider=request.provider,
            provider_session_id=request.state.conversation_id,
            messages=messages,
            temperature=request.temperature,
            tools=tools or None,
            tool_choice=tool_choice,
            metadata=metadata,
        )
        attempts = 0
        while True:
            attempts += 1
            self._ensure_run_control(request)
            request.budget.ensure_available(budget_stage)
            timeout = request.budget.operation_timeout(
                budget_stage,
                requested_seconds=request.max_model_call_seconds,
            )
            request.budget.record_model_call()
            request.state.model_calls += 1
            try:
                with request.budget.observe(
                    budget_stage,
                    metadata={
                        "provider": request.provider,
                        "model": request.model,
                        "attempt": attempts,
                    },
                ):
                    result = await asyncio.wait_for(
                        provider.achat(
                            llm_request,
                            tools=tools or None,
                            tool_choice=tool_choice,
                        ),
                        timeout=timeout,
                    )
                self._ensure_run_control(request)
                self._record_context_usage(
                    request,
                    self._context_usage_for_request(llm_request, result.context_usage),
                    attempts,
                )
                return result
            except asyncio.TimeoutError as exc:
                usage = self._context_usage_for_request(llm_request)
                self._record_context_usage(request, usage, attempts)
                error = LLMProviderRequestError(
                    provider=request.provider,
                    model=request.model,
                    stage="model_call",
                    code="model_call_timeout",
                    retryable=False,
                    category="provider_api",
                    context_usage=usage,
                    timeout_origin="provider_transport",
                    diagnostics={"exception_type": type(exc).__name__},
                )
                self._record_provider_failure(
                    request,
                    error,
                    attempts=attempts,
                    protocol=protocol,
                    endpoint_host=endpoint_host,
                )
                if request.budget.remaining_seconds() <= 0.001:
                    raise TimeoutError(
                        "The native agent run deadline expired during a model call."
                    ) from exc
                raise error from exc
            except LLMProviderRequestError as exc:
                self._record_context_usage(
                    request,
                    self._context_usage_for_request(llm_request, exc.context_usage),
                    attempts,
                )
                self._record_provider_failure(
                    request,
                    exc,
                    attempts=attempts,
                    protocol=protocol,
                    endpoint_host=endpoint_host,
                )
                if not exc.retryable or attempts >= self.transport_policy.max_attempts:
                    raise
                request.budget.record_retry()
                request.budget.ensure_available("model_retry")
                await asyncio.sleep(
                    min(
                        self.transport_policy.retry_delay(attempts),
                        request.budget.remaining_seconds(),
                    )
                )
                self._ensure_run_control(request)
                request.budget.ensure_available("model_retry")
            except (AgentRunControlSignal, LLMStructuredOutputError):
                raise
            except Exception as exc:
                normalized = LLMProviderRequestError.from_exception(
                    exc,
                    provider=request.provider,
                    model=request.model,
                    stage="model_call",
                    context_usage=self._context_usage_for_request(llm_request),
                )
                self._record_provider_failure(
                    request,
                    normalized,
                    attempts=attempts,
                    protocol=protocol,
                    endpoint_host=endpoint_host,
                )
                if not normalized.retryable or attempts >= self.transport_policy.max_attempts:
                    raise normalized from exc
                request.budget.record_retry()
                request.budget.ensure_available("model_retry")
                await asyncio.sleep(
                    min(
                        self.transport_policy.retry_delay(attempts),
                        request.budget.remaining_seconds(),
                    )
                )
                self._ensure_run_control(request)
                request.budget.ensure_available("model_retry")

    # -------------------------------------------------------------------------
    async def _checkpoint(self, request: AgentLoopRequest) -> None:
        """Persist a safe native state boundary when configured."""

        callback = request.checkpoint_callback
        if callback is None:
            return
        request.state.budget_snapshot = request.budget.snapshot()
        await callback(request.state)

    # -------------------------------------------------------------------------
    @staticmethod
    def _context_usage_for_request(
        llm_request: LLMRequest,
        provider_usage: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        base_usage = compute_context_usage(
            llm_request, provider=llm_request.provider or "unknown"
        )
        return merge_provider_context_usage(base_usage, provider_usage).to_dict()

    # -------------------------------------------------------------------------
    @staticmethod
    def _record_context_usage(
        request: AgentLoopRequest,
        usage: dict[str, Any] | None,
        attempt: int,
    ) -> None:
        if not isinstance(usage, dict):
            return
        trace_usage = {
            "phase": "native_loop",
            "model": request.model,
            "attempt": attempt,
            "model_call": request.state.model_calls,
            **dict(usage),
        }
        request.budget.record_context_allocation(trace_usage)
        request.state.context_usage_trace.append(dict(trace_usage))
        request.state.model_trace.append(
            {
                "attempt": attempt,
                "model_call": request.state.model_calls,
                "status": "observed",
                "estimated_input_tokens": trace_usage.get(
                    "estimated_input_tokens"
                ),
                "reported_input_tokens": trace_usage.get("reported_input_tokens"),
                "reported_output_tokens": trace_usage.get("reported_output_tokens"),
                "usage_source": trace_usage.get("usage_source"),
            }
        )
        callback = request.context_usage_callback
        if callback is None:
            return
        try:
            callback(dict(usage))
        except Exception:
            # Telemetry must not change the model/tool execution semantics.
            return

    # -------------------------------------------------------------------------
    @staticmethod
    def _provider_protocol(provider: AgentProvider, model: str) -> str:
        protocol_for_model = getattr(provider, "protocol_for_model", None)
        if callable(protocol_for_model):
            try:
                protocol = protocol_for_model(model)
            except Exception:
                protocol = None
            if isinstance(protocol, str) and protocol.strip():
                return protocol.strip()
        provider_name = str(getattr(provider, "provider_name", ""))
        return {
            "openai": "openai-responses",
            "google": "google-model",
            "deepseek": "openai-chat-completions",
            "ollama": "ollama-chat",
        }.get(provider_name, "unknown")

    # -------------------------------------------------------------------------
    @staticmethod
    def _provider_endpoint_host(provider: AgentProvider) -> str | None:
        base_url = getattr(provider, "base_url", None)
        if not isinstance(base_url, str) or not base_url:
            return None
        hostname = urlparse(base_url).hostname
        return hostname if hostname else None

    # -------------------------------------------------------------------------
    @staticmethod
    def _record_provider_failure(
        request: AgentLoopRequest,
        exc: LLMProviderRequestError,
        *,
        attempts: int,
        protocol: str,
        endpoint_host: str | None,
    ) -> None:
        diagnostics = dict(exc.diagnostics)
        request.state.model_trace.append(
            {
                "attempt": attempts,
                "model_call": request.state.model_calls,
                "status": "failed",
                "provider": request.provider,
                "model": request.model,
                "protocol": protocol,
                "endpoint_host": endpoint_host,
                "error_code": exc.code,
                "exception_class": diagnostics.get(
                    "exception_type", type(exc).__name__
                ),
                "win32_error": diagnostics.get("winerror"),
                "http_status": exc.http_status,
                "timeout_origin": exc.timeout_origin or "unknown",
                "retryable": exc.retryable,
                "diagnostics": diagnostics,
            }
        )

    # -------------------------------------------------------------------------
    async def _execute_calls(
        self,
        request: AgentLoopRequest,
        calls: list[LLMToolCall],
        state: AgentRunState,
        *,
        exposed_tool_names: Collection[str] | None = None,
    ) -> list[ToolResult]:
        tool_limit = request.budget.max_tool_calls or request.max_tool_calls
        remaining_tool_calls = tool_limit - state.tool_calls
        if remaining_tool_calls <= 0:
            raise ExecutionBudgetExceeded("tool_budget_exhausted", "tool_call")
        bounded_calls = calls[: min(request.max_parallel_tool_calls, remaining_tool_calls)]
        semaphore = asyncio.Semaphore(max(1, request.max_parallel_tool_calls))
        if any(call.name == "discover_geospatial_capabilities" for call in bounded_calls):
            state.discovery_attempts += sum(
                1
                for call in bounded_calls
                if call.name == "discover_geospatial_capabilities"
            )
        self._transition(state, AgentPhase.VALIDATE_ACTION, request.budget)

        async def execute(call: LLMToolCall) -> ToolResult:
            self._ensure_run_control(request)
            fingerprint = self._fingerprint(call)
            cached = state.successful_fingerprints.get(fingerprint)
            if cached is not None:
                if len(state.tool_trace) < 128:
                    state.tool_trace.append(
                        {
                            "call_id": call.id or cached.call_id,
                            "tool": call.name,
                            "status": cached.status,
                            "replayed": True,
                            "boundary": "loop_deduplication",
                        }
                    )
                return cached.model_copy(
                    update={"call_id": call.id or cached.call_id}, deep=True
                )
            failed_count = state.failed_fingerprints.get(fingerprint, 0)
            render_failed_count = state.failed_render_fingerprints.get(fingerprint, 0)
            if call.name == "apply_map_plan" and render_failed_count == 0:
                render_failed_count = sum(
                    1
                    for observation in state.render_observations
                    if observation.status == "failed"
                    and observation.action_fingerprint == fingerprint
                )
            if (
                call.name == "apply_map_plan"
                # A failed browser render is already proof that this exact
                # semantic map action made no progress.  Reject its first
                # repeat even though ordinary provider-call retries retain
                # the more permissive shared fingerprint limit.
                and render_failed_count >= 1
            ):
                return self._failure_result(
                    call,
                    "repeated_failed_render",
                    "The same map plan already failed browser rendering and was not repeated.",
                    recovery="replan",
                )
            if failed_count >= request.max_same_failed_fingerprint:
                if len(state.tool_trace) < 128:
                    state.tool_trace.append(
                        {
                            "call_id": call.id or "repeated-call",
                            "tool": call.name,
                            "status": "failed",
                            "error_code": "repeated_failed_fingerprint",
                            "recovery": "replan",
                            "boundary": "loop_deduplication",
                        }
                    )
                return self._failure_result(
                    call,
                    "repeated_failed_fingerprint",
                    "The same failing tool call was not repeated.",
                    recovery="replan",
                )
            async with semaphore:
                result = await self.tool_executor.execute_tool(
                    call,
                    state,
                    request.budget,
                    trace_callback=request.trace_callback,
                    iteration=state.current_iteration,
                    task_id=self._active_task_id(state),
                    exposed_tool_names=exposed_tool_names,
                )
                self._ensure_run_control(request)
                return result

        if any(call.name == "apply_map_plan" for call in bounded_calls):
            results: list[ToolResult] = []
            for call in bounded_calls:
                results.append(await execute(call))
        else:
            results = await asyncio.gather(*(execute(call) for call in bounded_calls))
        self._transition(state, AgentPhase.NORMALIZE_RESULT, request.budget)
        for call, result in zip(bounded_calls, results, strict=False):
            self._ensure_run_control(request)
            fingerprint = self._fingerprint(call)
            if result.status == "failed":
                state.failed_fingerprints[fingerprint] = (
                    state.failed_fingerprints.get(fingerprint, 0) + 1
                )
                if result.error and result.error.error_type in {
                    "malformed_call",
                    "tool_not_exposed",
                    "schema_validation",
                    "semantic_validation",
                    "policy_rejection",
                }:
                    state.validation_corrections += 1
            elif result.tool_name != "apply_map_plan":
                state.successful_fingerprints[fingerprint] = result
            elif result.status == "success":
                # Map candidates are only reusable after the browser proves
                # that this action rendered.  Keep the semantic action
                # fingerprint in the checkpoint so a failed candidate can be
                # rejected even though each retry receives a new session ID.
                state.prepared_map_action_fingerprint = fingerprint
            elif result.tool_name == "apply_map_plan":
                # A map-plan validation/build failure did not create a
                # candidate, so do not let a stale action fingerprint affect a
                # later, materially different correction.
                state.prepared_map_action_fingerprint = None
            self._ensure_run_control(request)
            self._apply_result(state, result)
        refreshed = await self._refresh_capabilities_after_location(
            request, state, results
        )
        if refreshed is not None:
            results.append(refreshed)
        return results

    # -------------------------------------------------------------------------
    async def _refresh_capabilities_after_location(
        self,
        request: AgentLoopRequest,
        state: AgentRunState,
        results: list[ToolResult],
    ) -> ToolResult | None:
        """Refresh the validated shortlist without spending a model turn."""

        route = state.route
        if (
            route is None
            or route.task_mode != "execute"
            or not route.requires_location
            or (
                route.primary_domain
                in {CapabilityDomain.MAP_RENDERING, CapabilityDomain.MAP_STATE}
                and not route.secondary_domains
            )
            or state.capability_ids
            or not any(
                result.tool_name == "resolve_geospatial_location"
                and result.status == "success"
                for result in results
            )
        ):
            return None
        registered = self.tool_registry.get("discover_geospatial_capabilities")
        if registered is None:
            return None
        tool_limit = request.budget.max_tool_calls or request.max_tool_calls
        if state.tool_calls >= tool_limit:
            return None
        call = LLMToolCall(
            id=f"server-discovery-refresh-{state.request_id}-{state.discovery_attempts + 1}",
            name="discover_geospatial_capabilities",
            arguments={"limit": 12},
        )
        self._ensure_run_control(request)
        state.discovery_attempts += 1
        self._transition(state, AgentPhase.VALIDATE_ACTION, request.budget)
        result = await self.tool_executor.execute_tool(
            call,
            state,
            request.budget,
            trace_callback=request.trace_callback,
            iteration=state.current_iteration,
            task_id=self._active_task_id(state),
            exposed_tool_names={"discover_geospatial_capabilities"},
        )
        self._ensure_run_control(request)
        self._transition(state, AgentPhase.NORMALIZE_RESULT, request.budget)
        self._apply_result(state, result)
        return result

    # -------------------------------------------------------------------------
    @staticmethod
    def _apply_result(state: AgentRunState, result: ToolResult) -> None:
        if not any(item.call_id == result.call_id for item in state.tool_results):
            state.tool_results.append(result)
        if result.status == "failed":
            state.consecutive_tool_failures += 1
            if (
                result.error is not None
                and result.error.recovery in {"choose_alternate_tool", "replan"}
                and result.tool_name == "execute_geospatial_capability"
            ):
                capability_id = result.metadata.capability_id
                if (
                    capability_id
                    and capability_id not in state.excluded_capability_ids
                ):
                    state.excluded_capability_ids.append(capability_id)
                # Re-open the discovery boundary after a provider/capability
                # failure.  Keeping only the failed ID would prevent the
                # model from selecting an equivalent source.
                state.capability_ids = []
            return
        if (
            result.tool_name == "execute_geospatial_capability"
            and result.status == "valid_empty"
        ):
            # An empty result is a useful observation, but it must not lock
            # the next decision to the same shortlist.  Re-open capability
            # discovery while retaining exclusions and the bounded result
            # observation so the model can broaden the query or select an
            # alternate source.
            state.capability_ids = []
        state.consecutive_tool_failures = 0
        for evidence_ref in result.evidence_refs:
            if evidence_ref not in state.evidence_refs:
                state.evidence_refs.append(evidence_ref)

    # -------------------------------------------------------------------------
    def _fingerprint(self, call: LLMToolCall) -> str:
        arguments = call.arguments
        registered = self.tool_registry.get(call.name)
        if registered is not None and isinstance(arguments, dict):
            try:
                arguments = registered.input_model.model_validate(
                    arguments
                ).model_dump(
                    mode="json", exclude_none=True, exclude_defaults=True
                )
            except Exception:
                # JSON object ordering is canonicalized by the serializer
                # below; retain malformed arguments for the typed executor.
                pass
        if call.name == "apply_map_plan" and isinstance(arguments, dict):
            # Collection revision is a server-owned CAS token. It changes on
            # every resumed attempt but does not make the semantic map action
            # materially different for render-recovery deduplication.
            arguments = {
                key: value
                for key, value in arguments.items()
                if key != "expected_collection_revision"
            }
        payload = {
            "name": call.name,
            "arguments": arguments,
            "parse_error": call.parse_error,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    # -------------------------------------------------------------------------
    @staticmethod
    def _first_render_failure(state: AgentRunState) -> Any | None:
        """Return the first bounded render failure for this run.

        Later observations may be generic follow-on validation failures. They
        must not replace the first decisive cause in recovery instructions or
        terminal text; the checkpoint retains the bounded chronological list.
        """

        for observation in state.render_observations:
            if observation.status == "failed":
                return observation
        return None

    # -------------------------------------------------------------------------
    @staticmethod
    def _no_progress_correction(state: AgentRunState) -> dict[str, Any]:
        pending = AgentLoop._pending_native_requirements(state)
        render_failure = AgentLoop._first_render_failure(state)
        if render_failure is not None:
            return {
                "observation_type": "failed_render_recovery",
                "status": "action_required",
                "pending_requirements": pending,
                "failure_code": render_failure.failure_code,
                "failure_stage": render_failure.failure_stage,
                "failure_summary": render_failure.failure_summary,
                "failed_action_fingerprint": render_failure.action_fingerprint,
                "message": (
                    "The previous map action failed browser rendering. Do not "
                    "repeat its action fingerprint; issue a materially revised "
                    "map plan or choose a supported renderable source."
                ),
            }
        return {
            "observation_type": "pending_requirements",
            "status": "action_required",
            "pending_requirements": pending,
            "message": (
                "The response did not complete the deterministic completion "
                "contract. Select and execute the next required tool action."
            ),
        }

    # -------------------------------------------------------------------------
    @staticmethod
    def _render_recovery_requires_map_action(
        state: AgentRunState,
        results: list[ToolResult],
    ) -> bool:
        """Require a new map candidate after a browser render failure."""

        return (
            not state.render_verified
            and state.prepared_map_session is None
            and AgentLoop._first_render_failure(state) is not None
            and not any(
                result.tool_name == "apply_map_plan"
                and result.status == "success"
                for result in results
            )
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def _evaluate_stop(
        state: AgentRunState,
        route: CapabilityRoute,
        results: list[ToolResult],
        *,
        max_consecutive_tool_failures: int,
        max_validation_corrections: int,
        max_discovery_attempts: int,
    ) -> tuple[str, str] | None:
        if state.prepared_map_session is not None:
            return "awaiting_render", "The map candidate is awaiting render acknowledgment."
        if state.validation_corrections >= max_validation_corrections:
            return "failed", "The agent stopped after repeated invalid tool calls."
        actionable_recovery = any(
            result.error is not None
            and result.error.recovery
            in {
                "correct_arguments",
                "retry_transport",
                "choose_alternate_tool",
                "replan",
            }
            for result in results
        )
        if any(
            result.error is not None
            and result.error.recovery == "request_user_input"
            for result in results
        ):
            question = next(
                result.error.message
                for result in results
                if result.error is not None
                and result.error.recovery == "request_user_input"
            )
            return "clarification_required", question
        if AgentLoop._render_recovery_requires_map_action(state, results):
            return (
                "no_progress",
                "Render recovery requires a materially different map action.",
            )
        if any(result.status != "failed" for result in results):
            if (
                all(result.status == "valid_empty" for result in results)
                and not state.capability_ids
                and state.discovery_attempts >= max_discovery_attempts
            ):
                return (
                    "insufficient_evidence",
                    "No supported capability matched the request after discovery.",
                )
            return None
        if results and all(result.status == "failed" for result in results):
            if state.consecutive_tool_failures >= max_consecutive_tool_failures:
                return "failed", "The agent stopped after repeated tool failures."
            if actionable_recovery:
                return None
            return "failed", "The requested tool could not complete successfully."
        return None

    # -------------------------------------------------------------------------
    @staticmethod
    def _evaluate_text_stop(
        state: AgentRunState,
        route: CapabilityRoute,
        text: str,
        *,
        available_tools: list[str] | None = None,
    ) -> tuple[str, str] | None:
        if route.task_mode == "clarify":
            return "clarification_required", text
        if state.prepared_map_session is not None:
            return "awaiting_render", text
        if text:
            tools = list(available_tools or [])
            pending = AgentLoop._pending_native_requirements(state)
            if pending:
                return (
                    "no_progress" if tools else "insufficient_evidence",
                    text,
                )
            if route.presentation in {"map", "both"}:
                # A verified render closes the presentation requirement.  The
                # finalization-only model call after a render acknowledgement
                # must be able to terminate successfully instead of being
                # mistaken for another no-progress map response.
                if state.render_verified:
                    return "goal_satisfied", text
                return (
                    "no_progress"
                    if tools and state.context_hydrated
                    else "insufficient_evidence",
                    text,
                )
            return "goal_satisfied", text
        return None

    # -------------------------------------------------------------------------
    async def _recover_location_only_map(
        self,
        request: AgentLoopRequest,
        route: CapabilityRoute,
        state: AgentRunState,
    ) -> list[ToolResult]:
        """Complete a location-only map when the model stops after resolving it.

        Some providers can return a polished final answer after a successful
        location lookup without issuing the required map-plan call.  Keep the
        completion contract server-owned for this narrow route: reuse the
        validated location and the normal typed tool boundary, without
        fabricating a layer or changing the configured provider/model.
        """

        if (
            not self._needs_location_only_map_recovery(state, route)
            or self.tool_registry.get("apply_map_plan") is None
        ):
            return []
        location_ref = self._location_only_map_recovery_ref(state, route)
        if location_ref is None:
            return []
        expected_revision = (
            state.active_map_session.overlay_collection.revision
            if state.active_map_session is not None
            else 0
        )
        recovery_call = LLMToolCall(
            id=f"server-location-map-recovery-{state.request_id}",
            name="apply_map_plan",
            arguments={
                "expected_collection_revision": expected_revision,
                "actions": [
                    {
                        "action": "set_viewport",
                        "strategy": "fit_location",
                        "location_ref": str(location_ref),
                    }
                ],
            },
        )

        return await self._execute_calls(
            request,
            [recovery_call],
            state,
            exposed_tool_names={"apply_map_plan"},
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def _location_only_map_recovery_ref(
        state: AgentRunState,
        route: CapabilityRoute | None = None,
    ) -> str | None:
        location_results = [
            result
            for result in state.tool_results
            if result.tool_name == "resolve_geospatial_location"
            and result.status == "success"
        ]
        target_ids = [
            str(result.data.get("target_id") or "").strip()
            for result in location_results
            if isinstance(result.data, dict)
            and str(result.data.get("target_id") or "").strip()
        ]
        normalized_target_ids = {
            " ".join(target_id.casefold().split()) for target_id in target_ids
        }
        if target_ids and len(target_ids) == len(location_results) and len(
            normalized_target_ids
        ) == 1:
            target_id = target_ids[0]
            if target_id in state.location_refs:
                return target_id
            normalized_target_id = target_id.casefold()
            for location_ref in state.location_refs:
                if location_ref.casefold() == normalized_target_id:
                    return location_ref
            return None
        if not location_results and len(state.location_refs) == 1:
            return next(iter(state.location_refs))
        if not location_results and route is not None and len(route.target_refs) == 1:
            target_ref = " ".join(route.target_refs[0].casefold().split())
            close_matches = [
                location_ref
                for location_ref in state.location_refs
                if SequenceMatcher(
                    None,
                    " ".join(location_ref.casefold().split()),
                    target_ref,
                ).ratio()
                >= 0.9
            ]
            if len(close_matches) == 1:
                return close_matches[0]
        return None

    # -------------------------------------------------------------------------
    @staticmethod
    def _needs_location_only_map_recovery(
        state: AgentRunState,
        route: CapabilityRoute,
    ) -> bool:
        if (
            route.task_mode != "execute"
            or route.primary_domain is not CapabilityDomain.MAP_RENDERING
            or route.presentation not in {"map", "both"}
            or route.secondary_domains
            or state.prepared_map_session is not None
        ):
            return False
        contract = state.completion_contract
        if contract is None or not contract.map_preparation_required:
            return False
        if contract.evidence_required:
            return False
        # The contract, not a vocabulary allow-list, determines whether this
        # is a location-only presentation.  Capability choice remains the
        # model's responsibility for hydrated native runs.
        return AgentLoop._location_only_map_recovery_ref(state, route) is not None

    # -------------------------------------------------------------------------
    @staticmethod
    def _ensure_run_control(request: AgentLoopRequest) -> None:
        check = request.run_state_check
        if check is None:
            return
        signal = str(check() or "").strip().casefold()
        if signal in {"cancelled", "canceled", "cancel_requested"}:
            raise AgentRunControlSignal("cancelled")
        if signal in {"superseded", "superseded_by_steering", "stale"}:
            raise AgentRunControlSignal("superseded")

    # -------------------------------------------------------------------------
    @staticmethod
    def _transition(
        state: AgentRunState,
        phase: AgentPhase,
        budget: AgentExecutionBudget | None = None,
        *,
        count: bool = True,
    ) -> None:
        previous = state.phase.value
        if state.phase is phase:
            return
        if count and budget is not None:
            budget.record_transition()
        state.phase = phase
        if count:
            state.transitions += 1
        state.transition_trace.append({"from": previous, "to": phase.value})

    # -------------------------------------------------------------------------
    @staticmethod
    def _initial_messages(request: AgentLoopRequest) -> list[dict[str, Any]]:
        state = request.state
        if state.context_hydrated:
            return build_native_context_messages(
                current_user_message=state.user_message,
                recent_messages=state.recent_messages,
                active_directives=state.active_directives,
                task_state=state.task_state,
                map_memory=state.map_memory,
                summary=state.summary,
                relevant_tool_outcomes=state.relevant_tool_outcomes,
                render_observations=[
                    item.model_dump(mode="json")
                    for item in state.render_observations[-8:]
                ],
                policy_constraints=state.policy_constraints,
                context_selection={
                    "included_message_ids": state.included_message_ids,
                    "omitted_message_ids": state.omitted_message_ids,
                    "summarized_through_turn_index": state.summarized_through_turn_index,
                },
            )
        return list(request.messages) or [
            {"role": "user", "content": state.user_message}
        ]

    # -------------------------------------------------------------------------
    @staticmethod
    def _budget_profile(route: CapabilityRoute) -> str:
        if (
            route.presentation in {"map", "both"}
            or route.secondary_domains
            or len(route.capability_queries) > 1
            or route.primary_domain is CapabilityDomain.SPATIAL_ANALYSIS
        ):
            return "complex"
        return "simple"

    # -------------------------------------------------------------------------
    @staticmethod
    def _compile_native_goal(state: AgentRunState, route: CapabilityRoute) -> None:
        route_temporal_scope = route.temporal_scope.model_dump(mode="json")
        route_has_temporal_scope = any(
            route_temporal_scope.get(key)
            for key in (
                "reference_time_iso",
                "start_time_iso",
                "end_time_iso",
            )
        ) or route_temporal_scope.get("mode") != "none" or any(
            route_temporal_scope.get(key) not in {None, "none", ""}
            for key in ("granularity", "aggregation")
        )
        operation = route.operation or route.primary_domain.value
        spatial_target_refs = (
            route.spatial_scope.target_refs if route.spatial_scope is not None else []
        )
        target_ids = list(
            dict.fromkeys(
                str(item).strip()
                for item in [*route.target_refs, *spatial_target_refs]
                if str(item).strip()
            )
        )
        temporal_scope = route_temporal_scope if route_has_temporal_scope else {}
        spatial_scope = (
            [route.spatial_scope.model_dump(mode="json")]
            if route.spatial_scope is not None
            else []
        )
        filters = dict(route.filters)
        requirements: list[str] = []
        if route.requires_location:
            requirements.append("location_resolved")
        route_domains = {route.primary_domain, *route.secondary_domains}
        data_route = (
            CapabilityDomain.DATA_RETRIEVAL in route_domains
            or route.primary_domain
            not in {CapabilityDomain.MAP_RENDERING, CapabilityDomain.MAP_STATE}
        )
        requires_provider_data = (
            route.task_mode == "execute"
            and data_route
            and not _is_location_only_map_request(state.user_message, route)
        )
        if requires_provider_data:
            requirements.append("required_data_retrieved")
        if route.task_mode == "execute" and route_has_temporal_scope and temporal_scope and (
            temporal_scope.get("mode") != "none"
            or temporal_scope.get("start_time_iso") is not None
            or temporal_scope.get("end_time_iso") is not None
            or temporal_scope.get("reference_time_iso") is not None
        ):
            requirements.append("temporal_scope_applied")
        if route.task_mode == "execute" and route.spatial_scope is not None:
            requirements.append("spatial_scope_applied")
        if route.presentation in {"map", "both"}:
            requirements.append("map_candidate_prepared")
        state.completion_requirements = list(dict.fromkeys(requirements))
        state.goal = AgentGoal(
            goal=state.user_message,
            task_mode=route.task_mode,
            presentation=route.presentation,
            operation=operation,
            requires_location=route.requires_location,
            target_ids=target_ids,
            temporal_scope=temporal_scope,
            spatial_scope=spatial_scope,
            filters=filters,
        )
        state.completion_contract = CompletionContract(
            operation=operation,
            data_requirement=("provider_data" if requires_provider_data else "none"),
            requirements=list(state.completion_requirements),
            location_required=route.requires_location,
            evidence_required="required_data_retrieved" in state.completion_requirements,
            map_preparation_required="map_candidate_prepared"
            in state.completion_requirements,
            temporal_scope_required=bool(
                temporal_scope
                and (
                    temporal_scope.get("mode") != "none"
                    or temporal_scope.get("start_time_iso") is not None
                    or temporal_scope.get("end_time_iso") is not None
                    or temporal_scope.get("reference_time_iso") is not None
                )
            ),
            spatial_scope_required=bool(spatial_scope),
            render_verification_required=route.presentation in {"map", "both"},
            render_verified=state.render_verified,
        )
        AgentLoop._initialize_task_state_for_route(state, route)

    # -------------------------------------------------------------------------
    @staticmethod
    def _pending_native_requirements(state: AgentRunState) -> list[str]:
        if not state.context_hydrated or state.completion_contract is None:
            return []
        # Scope is bound by the server-owned execution adapter.  A
        # successful/empty/partial capability observation therefore proves
        # that the selected temporal and spatial contract was applied to the
        # provider request, without trusting model-supplied geometry.
        checks = AgentLoop._completion_checks(state)
        required_names = list(state.completion_contract.requirements)
        if (
            state.completion_contract.temporal_scope_required
            and "temporal_scope_applied" not in required_names
        ):
            required_names.append("temporal_scope_applied")
        if (
            state.completion_contract.spatial_scope_required
            and "spatial_scope_applied" not in required_names
        ):
            required_names.append("spatial_scope_applied")
        if (
            state.completion_contract.render_verification_required
            and "render_verified" not in required_names
            and state.render_observations
        ):
            # Before the first candidate is prepared, map_candidate_prepared
            # is the actionable obligation. Once the browser has reported a
            # result, expose the explicit render requirement so a failed
            # observation drives a correction rather than a false completion.
            required_names.append("render_verified")
        return [
            name
            for name in required_names
            if not checks.get(name, False)
        ]

    # -------------------------------------------------------------------------
    @staticmethod
    def _working_state_message(state: AgentRunState, limit: int) -> str:
        tool_result_summaries: list[dict[str, Any]] = [
            {
                "call_id": item.call_id,
                "tool_name": item.tool_name,
                "status": item.status,
                "summary": item.summary,
                "evidence_refs": list(item.evidence_refs),
                "error_code": item.error.code if item.error else None,
            }
            for item in state.tool_results[-8:]
        ]
        payload: dict[str, Any] = {
            "phase": state.phase.value,
            "goal": (
                state.goal.model_dump(mode="json")
                if state.goal is not None
                else None
            ),
            "completion_contract": (
                state.completion_contract.model_dump(mode="json")
                if state.completion_contract is not None
                else None
            ),
            "route": state.route.model_dump(mode="json") if state.route else None,
            "capability_ids": list(state.capability_ids),
            "excluded_capability_ids": list(state.excluded_capability_ids),
            "location_refs": sorted(state.location_refs),
            "evidence_refs": list(state.evidence_refs),
            "prepared_map": bool(state.prepared_map_session),
            "render_verified": state.render_verified,
            "render_attempts": state.render_attempts,
            "render_observations": [
                item.model_dump(mode="json") for item in state.render_observations[-4:]
            ],
            "active_map_collection_revision": (
                state.active_map_session.overlay_collection.revision
                if state.active_map_session is not None
                else 0
            ),
            "tool_results": tool_result_summaries,
        }
        serialized = json.dumps(payload, separators=(",", ":"), default=str)
        if len(serialized) <= max(256, limit):
            return serialized
        compact = dict(payload)
        compact["tool_results"] = [
            {
                "tool_name": item["tool_name"],
                "status": item["status"],
                "summary": str(item["summary"])[:240],
                "error_code": item["error_code"],
            }
            for item in tool_result_summaries[-3:]
        ]
        compact["evidence_refs"] = list(state.evidence_refs[-8:])
        serialized = json.dumps(compact, separators=(",", ":"), default=str)
        if len(serialized) <= max(256, limit):
            return serialized
        minimal = {
            "phase": state.phase.value,
            "goal": AgentLoop._compact_goal(state),
            "completion_contract": AgentLoop._compact_completion_contract(state),
            "route": AgentLoop._compact_route(state),
            "capability_ids": list(state.capability_ids[:12]),
            "location_refs": sorted(state.location_refs)[:12],
            "evidence_refs": list(state.evidence_refs[-8:]),
            "prepared_map": bool(state.prepared_map_session),
            "render_verified": state.render_verified,
            "render_attempts": state.render_attempts,
            "render_observations": [
                item.model_dump(mode="json") for item in state.render_observations[-2:]
            ],
        }
        return json.dumps(minimal, separators=(",", ":"), default=str)

    # -------------------------------------------------------------------------
    @staticmethod
    def _compact_goal(state: AgentRunState) -> dict[str, Any] | None:
        if state.goal is None:
            return None
        return {
            "goal": state.goal.goal[:500],
            "task_mode": state.goal.task_mode,
            "presentation": state.goal.presentation,
            "operation": state.goal.operation,
            "requires_location": state.goal.requires_location,
            "target_ids": list(state.goal.target_ids[:16]),
            "temporal_scope": state.goal.temporal_scope,
            "spatial_scope": list(state.goal.spatial_scope[:16]),
            "filters": {
                str(key): value
                for key, value in list(state.goal.filters.items())[:16]
            },
        }

    # -------------------------------------------------------------------------
    @staticmethod
    def _compact_completion_contract(state: AgentRunState) -> dict[str, Any] | None:
        if state.completion_contract is None:
            return None
        return {
            "operation": state.completion_contract.operation,
            "data_requirement": state.completion_contract.data_requirement,
            "requirements": list(state.completion_contract.requirements[:16]),
            "location_required": state.completion_contract.location_required,
            "evidence_required": state.completion_contract.evidence_required,
            "map_preparation_required": state.completion_contract.map_preparation_required,
            "temporal_scope_required": state.completion_contract.temporal_scope_required,
            "spatial_scope_required": state.completion_contract.spatial_scope_required,
            "render_verification_required": state.completion_contract.render_verification_required,
            "render_verified": state.completion_contract.render_verified,
        }

    # -------------------------------------------------------------------------
    @staticmethod
    def _compact_route(state: AgentRunState) -> dict[str, Any] | None:
        if state.route is None:
            return None
        return {
            "primary_domain": state.route.primary_domain.value,
            "secondary_domains": [item.value for item in state.route.secondary_domains[:3]],
            "task_mode": state.route.task_mode,
            "presentation": state.route.presentation,
            "requires_location": state.route.requires_location,
            "capability_queries": list(state.route.capability_queries[:4]),
            "explicit_capability_ids": list(state.route.explicit_capability_ids[:8]),
            "operation": state.route.operation,
        }

    # -------------------------------------------------------------------------
    @staticmethod
    def _assistant_and_tool_messages(result: LLMResult) -> list[dict[str, Any]]:
        raw_output = result.raw.get("output")
        if is_json_array(raw_output):
            protocol_items: list[dict[str, Any]] = []
            for item in raw_output:
                if not is_json_object(item):
                    continue
                if str(item.get("type") or "") in {
                    "message",
                    "reasoning",
                    "function_call",
                }:
                    protocol_items.append(item)
            if protocol_items:
                # Responses-compatible providers require the returned
                # reasoning/function-call items to remain in the next input.
                # Keep them opaque to the native state and let the provider
                # adapter normalize them for its protocol.
                return protocol_items
        return [
            {
                "role": "assistant",
                "content": result.content or None,
                "tool_calls": [
                    {
                        "id": call.id,
                        "name": call.name,
                        "arguments": call.arguments or {},
                    }
                    for call in result.tool_calls
                ],
            }
        ]

    # -------------------------------------------------------------------------
    @staticmethod
    def _tool_result_messages(
        calls: list[LLMToolCall],
        results: list[ToolResult],
        *,
        max_chars: int = 4096,
    ) -> list[dict[str, Any]]:
        return [
            {
                "role": "tool",
                "tool_call_id": call.id,
                "name": call.name,
                "content": ModelObservation.from_tool_result(
                    result, max_chars=max_chars
                ).model_dump_json(exclude_none=True),
            }
            for call, result in zip(calls, results, strict=False)
        ]

    # -------------------------------------------------------------------------
    @staticmethod
    def _failure_result(
        call: LLMToolCall,
        code: str,
        message: str,
        *,
        recovery: Literal[
            "correct_arguments",
            "retry_transport",
            "choose_alternate_tool",
            "replan",
            "request_user_input",
            "terminal",
        ],
    ) -> ToolResult:
        return ToolResult(
            call_id=call.id or "repeated-call",
            tool_name=call.name,
            status="failed",
            summary=message,
            error=ToolExecutionError(
                error_type="state_conflict",
                code=code,
                message=message,
                retryable=False,
                recovery=recovery,
            ),
            metadata=ToolExecutionMetadata(duration_ms=0),
        )

    # -------------------------------------------------------------------------
    def _outcome(
        self,
        state: AgentRunState,
        final_text: str,
        reason: str,
        request: AgentLoopRequest,
    ) -> AgentLoopOutcome:
        self._sync_task_state(state)
        self._set_terminal_task_state(state, reason)
        state.budget_snapshot = request.budget.snapshot()
        target_phase = (
            AgentPhase.AWAIT_RENDER
            if reason == "awaiting_render"
            else AgentPhase.FAILED
            if reason in {"failed", "provider_error", "run_deadline_exhausted"}
            else AgentPhase.FINALIZE
        )
        try:
            self._transition(state, target_phase, request.budget)
        except ExecutionBudgetExceeded:
            # The terminal record itself must remain writable when the last
            # permitted transition was consumed by the failed operation.
            self._transition(state, target_phase, count=False)
        final_text = self._preserve_render_failure_cause(
            state, final_text, reason
        )
        state.budget_snapshot = request.budget.snapshot()
        return AgentLoopOutcome(
            final_text=final_text,
            state=state,
            stopped_reason=reason,  # type: ignore[arg-type]
            model_calls=state.model_calls,
            tool_results=list(state.tool_results),
        )

    # -------------------------------------------------------------------------
    def _failed(
        self,
        state: AgentRunState,
        request: AgentLoopRequest,
        detail: str,
        *,
        category: str,
    ) -> AgentLoopOutcome:
        state.termination_reason = "failed"
        self._sync_task_state(state)
        self._set_terminal_task_state(state, "failed")
        state.budget_snapshot = request.budget.snapshot()
        try:
            self._transition(state, AgentPhase.FAILED, request.budget)
        except ExecutionBudgetExceeded:
            self._transition(state, AgentPhase.FAILED, count=False)
        detail = self._preserve_render_failure_cause(state, detail, "failed")
        return AgentLoopOutcome(
            final_text=detail,
            state=state,
            stopped_reason="failed",
            model_calls=state.model_calls,
            tool_results=list(state.tool_results),
            failure_category=category,
            failure_detail=detail,
        )

    # -------------------------------------------------------------------------
    def _budget_outcome(
        self,
        state: AgentRunState,
        request: AgentLoopRequest,
        reason: str,
    ) -> AgentLoopOutcome:
        state.termination_reason = reason
        request.budget.terminal_reason = reason
        request.budget.stopping_reason = reason
        self._sync_task_state(state)
        self._set_terminal_task_state(state, reason)
        state.budget_snapshot = request.budget.snapshot()
        self._transition(state, AgentPhase.FAILED, count=False)
        final_text = self._preserve_render_failure_cause(
            state,
            "The agent reached its configured execution limit.",
            reason,
        )
        return AgentLoopOutcome(
            final_text=final_text,
            state=state,
            stopped_reason=reason,  # type: ignore[arg-type]
            model_calls=state.model_calls,
            tool_results=list(state.tool_results),
            # Keep the stop reason intact.  Context pressure, a transition
            # limit, and a no-progress guard have different remediation paths.
            failure_category=reason,
            failure_detail=final_text,
        )

    # -------------------------------------------------------------------------
    @classmethod
    def _preserve_render_failure_cause(
        cls, state: AgentRunState, text: str, reason: str
    ) -> str:
        if reason in {"awaiting_render", "goal_satisfied"} or state.render_verified:
            return text
        observation = cls._first_render_failure(state)
        if observation is None:
            return text
        code = observation.failure_code or "render_failed"
        marker = f"Previous map render failed ({code})"
        if marker in text:
            return text
        stage = (
            f" during {observation.failure_stage}"
            if observation.failure_stage
            else ""
        )
        summary = (
            observation.failure_summary
            or "The renderer did not verify the prepared map."
        )
        suffix = (
            f"{marker}{stage}: {summary} "
            "The last-known-good map was left unchanged."
        )
        return f"{text.rstrip()}\n\n{suffix}" if text.strip() else suffix


###############################################################################
def _is_location_only_map_request(
    user_message: str, route: CapabilityRoute
) -> bool:
    """Keep named-place display separate from provider-data retrieval."""

    if route.presentation not in {"map", "both"}:
        return False
    if route.primary_domain is not CapabilityDomain.PLACE_SEARCH:
        return False
    terms = set(re.findall(r"[a-z0-9]+", user_message.casefold()))
    if not terms.intersection(
        {"show", "display", "view", "locate", "map", "landmark"}
    ):
        return False
    return not terms.intersection(
        {
            "find",
            "search",
            "near",
            "nearby",
            "within",
            "around",
            "poi",
            "amenity",
            "amenities",
            "cafe",
            "cafes",
            "hospital",
            "hospitals",
            "station",
            "stations",
            "data",
            "points",
        }
    )


__all__ = [
    "AgentLoop",
    "AgentLoopOutcome",
    "AgentLoopRequest",
]
