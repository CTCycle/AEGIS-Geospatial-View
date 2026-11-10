"""Unified native state machine for bounded agent execution."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import hashlib
import inspect
import json
import logging
import re
from collections.abc import Awaitable, Collection, Sequence
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any, Callable, Literal, Protocol
from urllib.parse import urlparse

from pydantic import ValidationError

from server.common.identifiers import location_ref_matches, normalize_target_key
from server.common.logging_handlers import log_unexpected_failure
from server.common.typing import is_json_array, is_json_object, json_array, json_object
from server.contracts.geospatial import MapSession
from server.domain.agent.capability_route import (
    AgentGoal,
    AgentPhase,
    AgentRunState,
    AgentTask,
    AgentTaskState,
    AgentTemporalScope,
    CapabilityRoute,
    CompletionStatus,
    CompletionContract,
    CompletionRequirementKind,
    CompletionRequirement,
    LoopDecision,
    RequestObligation,
    TaskStatus,
    derive_request_obligations,
    dropped_obligations,
    places_named_in,
    same_target,
    unrouted_obligations,
)
from server.domain.agent.context import AgentContextView
from server.domain.agent.decision import normalize_clarification_options
from server.domain.agent.presentation_contract import CompletionSummary
from server.domain.agent.task_ledger import compatible_tasks, freshness_seconds
from server.domain.agent.map_plan import (
    PLACE_MARKERS_INSTANCE_ID,
    is_mark_locations_operation,
)
from server.domain.agent.capability_domains import CapabilityDomain
from server.domain.agent.reliability import (
    AgentExecutionBudget,
    ExecutionBudgetExceeded,
)
from server.domain.agent.trace import AgentTraceEvent, TraceKind, redact_trace_value
from server.domain.agent.tool_result import (
    ModelObservation,
    ToolExecutionError,
    ToolExecutionMetadata,
    ToolResult,
)
from server.domain.llm.types import LLMRequest, LLMResult, LLMToolCall, LLMToolDefinition
from server.prompts.agent import (
    NATIVE_CONTEXT_PREFIX,
    build_native_agent_system_prompt,
    build_native_context_messages,
)
from server.prompts.capability_route import build_capability_route_prompt
from server.services.agent.basemap_intent import (
    basemap_label,
    match_requested_basemaps,
    unsupported_basemap_styles,
)
from server.services.agent.capability_router import (
    CapabilityRouter,
    build_conversation_fallback_route,
    build_location_map_fallback_route,
    is_location_only_map_request,
)
from server.services.agent.context_assembler import select_pair_safe_messages
from server.services.agent.final_answer_check import (
    check_final_answer,
    drop_unsupported_time_zone_claims,
    only_omissions,
)
from server.services.agent.tool_executor import (
    UNSUPPORTED_CODES,
    ToolExecutor,
    build_rejection_feedback,
)
from server.services.agent.completion import (
    RASTER_ONLY_CODE,
    CompletionEvaluator,
    build_completion_summary,
    data_verified_empty,
    describe_requirements,
    evidence_coordinates,
    evidence_numbers,
    evidence_utc_offsets,
    imagery_only_note,
    key_names_variable,
    layer_edit_count,
    map_layer_counts,
    needs_numeric_values,
    prior_evidence_numbers,
    requested_transform_unmet,
    unmarked_route_targets,
)
from server.services.agent.policy_engine import (
    is_text_location_lookup,
    route_allows_capability_execution,
)
from server.services.agent.tool_registry import (
    analysis_complete,
    route_target_location_available,
    ToolRegistry,
    resolved_route_target_names,
    unresolved_route_targets,
)
from server.services.agent.vision_policy import (
    ITERATION_CALL_KIND,
    TERMINAL_CALL_KIND,
    VisionPolicyEngine,
)
from server.services.llm.context_budget import (
    estimate_input_sections,
    compute_context_usage,
    merge_provider_context_usage,
)
from server.services.llm.errors import LLMProviderRequestError, LLMStructuredOutputError
from server.services.llm.multimodal import attach_image, messages_contain_image
from server.services.llm.request_deadline import REQUEST_DEADLINE_METADATA_KEY
from server.services.llm.transport import LLMTransportPolicy

LOGGER = logging.getLogger(__name__)

USER_IMAGE_CAPTION = (
    "Image attached by the user to this request. Use its visual clues as evidence "
    "about the place or subject; a location inferred from it is a hypothesis."
)
USER_IMAGE_UNSUPPORTED_NOTE = (
    "The user attached an image, but the selected model cannot view images. Say so "
    "and do not describe or guess its content."
)

# Failures caused by the external source rather than by the call itself.
_PROVIDER_FAILURE_TYPES = frozenset(
    {"timeout", "rate_limit", "provider_unavailable", "provider_malformed_response"}
)

# Transient source failures that earn one retry before the target is failed.
_TRANSIENT_FAILURE_TYPES = frozenset({"timeout", "rate_limit"})

# Tools whose successful results are evidence worth listing in a fallback.
_EVIDENCE_TOOLS = frozenset(
    {
        "resolve_geospatial_location",
        "execute_geospatial_capability",
        "transform_evidence",
        "measure_geospatial",
    }
)

# Tools whose unavailability shows the route misread the request.
_ROUTE_DATA_TOOLS = frozenset(
    {
        "execute_geospatial_capability",
        "discover_geospatial_capabilities",
        "inspect_evidence",
        "transform_evidence",
    }
)

# Tool errors the model can fix on its next call.
_CORRECTABLE_ERRORS = frozenset(
    {
        "malformed_call",
        "tool_not_exposed",
        "unknown_tool",
        "schema_validation",
        "semantic_validation",
    }
)

# Terminal causes of a run that stopped on invalid tool calls, mapped to the
# public stop reason and failure category: an unsupported request is a
# disclosed limitation, an incapable model is a model-capability failure.
_TERMINAL_CAUSES: dict[str, tuple[str, str | None]] = {
    "unsupported_request": ("insufficient_evidence", None),
    "model_incapable": ("failed", "model_capability"),
}

# DeepSeek tool-call markup; models emit single or doubled full-width or ASCII bars.
_DSML_MARKUP = re.compile(r"<\s*/?\s*[｜|]{1,2}\s*dsml\s*[｜|]{1,2}", re.IGNORECASE)

_LIMIT_LABELS = {
    "iteration_budget_exhausted": "iteration limit",
    "model_budget_exhausted": "model-call limit",
    "tool_budget_exhausted": "tool-call limit",
    "transition_budget_exhausted": "state-transition limit",
    "no_progress": "repetition guard",
}

# Tools whose results can move each completion requirement. Scope checks are
# judged on evidence, so only evidence-producing tools can close them.
_SCOPE_EVIDENCE_TOOLS = frozenset(
    {"execute_geospatial_capability", "inspect_evidence", "transform_evidence"}
)
_REQUIREMENT_TOOLS: dict[str, frozenset[str]] = {
    "location_resolved": frozenset({"resolve_geospatial_location"}),
    "search_area_bound": frozenset({"resolve_geospatial_location"}),
    "capabilities_discovered": frozenset({"discover_geospatial_capabilities"}),
    "result_locations_derived": frozenset({"transform_evidence"}),
    "requested_transform_applied": frozenset({"transform_evidence"}),
    "measurement_computed": frozenset({"measure_geospatial"}),
    "evidence_inspected": frozenset({"inspect_evidence"}),
    "required_data_retrieved": _SCOPE_EVIDENCE_TOOLS,
    "temporal_scope_applied": _SCOPE_EVIDENCE_TOOLS | {"apply_map_plan"},
    "spatial_scope_applied": _SCOPE_EVIDENCE_TOOLS | {"apply_map_plan"},
    "map_candidate_prepared": frozenset({"apply_map_plan"}),
    "locations_marked": frozenset({"apply_map_plan"}),
    "render_verified": frozenset({"apply_map_plan"}),
}
# Tools that only derive from evidence the run already holds.
_DERIVATION_TOOLS = frozenset({"inspect_evidence", "transform_evidence", "measure_geospatial"})

###############################################################################
def _layer_count_text(count: tuple[int, int] | None) -> str:
    """" (91 records)" for a complete layer, " (25 of 91 records shown)" for a cut one."""

    if count is None:
        return ""
    shown, total = count
    if shown < total:
        return f" ({shown} of {total} records shown)"
    return f" ({total} record{'s' if total != 1 else ''})"

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

    # -------------------------------------------------------------------------
    def supports_vision(self, model: str) -> bool | None: ...

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
    max_model_call_seconds: float = 120.0
    max_iterations: int = 40
    max_model_calls: int = 30
    max_tool_calls: int = 60
    max_state_transitions: int = 200
    simple_max_model_calls: int = 12
    simple_max_tool_calls: int = 20
    simple_max_state_transitions: int = 100
    max_parallel_tool_calls: int = 8
    max_consecutive_tool_failures: int = 5
    max_same_failed_fingerprint: int = 3
    max_route_corrections: int = 2
    max_validation_corrections: int = 4
    max_discovery_attempts: int = 4
    max_tool_result_chars: int = 16384
    max_no_progress_corrections: int = 3
    max_unproductive_steps: int = 5
    max_render_attempts: int = 5
    vision_policy: str = "disabled"
    vision_max_calls: int = 2
    max_output_tokens: int = 32768
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
    # Set only when the loop suspends for a render handshake: whether the
    # browser should capture the rendered map for a vision-enabled model step.
    vision_capture_requested: bool = False

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
        capture_store: Any | None = None,
    ) -> None:
        self.provider_factory = provider_factory
        self.capability_router = capability_router
        self.tool_registry = tool_registry
        self.tool_executor = tool_executor
        self.transport_policy = transport_policy or LLMTransportPolicy()
        self.capture_store = capture_store

    # -------------------------------------------------------------------------
    async def run(self, request: AgentLoopRequest) -> AgentLoopOutcome:
        state = request.state
        provider = self.provider_factory.get_provider(request.provider)
        messages = self._initial_messages(request)
        final_text = ""
        state.max_iterations = max(1, int(request.max_iterations))
        self._ensure_task_state(state, request.max_iterations)
        self._attach_client_map_view(state)
        request.budget.configure_limits(
            max_model_calls=request.max_model_calls,
            max_tool_calls=request.max_tool_calls,
            max_state_transitions=request.max_state_transitions,
        )
        try:
            self._ensure_run_control(request)
            self._transition(state, AgentPhase.ROUTE_REQUEST, request.budget)
            resumed_route = state.route is not None
            route_result = (
                (None, "", state.route)
                if state.route is not None
                else self._fast_route(request)
                or await self._route(request, provider, messages)
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
            self._bind_search_area(state, route)
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
            self._compile_native_goal(
                state,
                route,
                requests_entities=self.capability_router.requests_catalog_entities(
                    state.user_message
                ),
                servable_queries=self.capability_router.capability_registry.servable_queries,
            )
            if not resumed_route:
                # Intent verification: a route that cannot carry every part of
                # the request is revised before any tool runs, not discovered
                # missing at completion.
                violation = self._obligation_violation(state)
                if violation is not None and await self._revise_route(
                    request, provider, messages, route, [], [],
                    reason=violation[0], missing=violation[1],
                ):
                    route = state.route or route
            self._narrow_prior_tasks(state)
            await self._refresh_capabilities_after_location(request, state, [])
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
            return await self._exhausted_outcome(request, provider, messages, exc.reason)
        except LLMProviderRequestError as exc:
            if exc.timeout_origin == "application_deadline":
                state.termination_reason = "run_deadline_exhausted"
                return self._outcome(
                    state,
                    final_text,
                    "run_deadline_exhausted",
                    request,
                )
            transport_failure = exc.retryable or exc.timeout_origin == "provider_transport"
            return self._failed(
                state,
                request,
                (
                    "The model provider could not be reached or answered with a "
                    f"transient error ({exc.code}) and retries did not recover. "
                    "This is a model-service outage, not a map-data failure; try again shortly."
                    if transport_failure
                    else "The selected model could not complete this request."
                ),
                category=exc.category,
            )
        except TimeoutError:
            state.termination_reason = "run_deadline_exhausted"
            return self._outcome(state, final_text, "run_deadline_exhausted", request)
        except LLMStructuredOutputError as exc:
            return self._failed(state, request, "The selected model could not complete this request.", category=exc.category)
        except Exception as exc:
            log_unexpected_failure(
                LOGGER, exc, stage="agent_loop", run_id=state.run_id or state.request_id,
                phase=state.phase.value, iteration=state.current_iteration,
            )
            return self._failed(state, request, "The agent stopped after an unexpected execution failure.", category="internal_error")

    # -------------------------------------------------------------------------
    def _narrow_prior_tasks(self, state: AgentRunState) -> None:
        """Keep only the ledger tasks the compiled goal may reuse."""

        if state.goal is None or not state.prior_tasks:
            return
        registry = self.capability_router.capability_registry
        state.prior_tasks = compatible_tasks(
            state.prior_tasks,
            state.goal,
            freshness=lambda capability_id: freshness_seconds(
                registry.get_capability(capability_id) if capability_id else None
            ),
            now=datetime.now(UTC),
        )

    # -------------------------------------------------------------------------
    def _attach_client_map_view(self, state: AgentRunState) -> None:
        """Expose the view the user saw when sending the request.

        It is client-reported: it tells the model where the user is looking
        and which layers they hid, while committed map state stays the
        server's record. A checkpoint keeps it across resumes.
        """

        capture_store = getattr(self, "capture_store", None)
        if capture_store is None:
            return
        view = capture_store.map_view_for_run(state.run_id or state.request_id)
        if view is not None:
            state.map_memory = {
                **state.map_memory,
                "current_view": {**view, "source": "client_reported"},
            }

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
                state.route or route,
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
        catalog_cursor = self._pending_catalog_discovery_cursor(state)
        if state.model_calls >= model_limit and catalog_cursor is None:
            return await self._exhausted_outcome(
                request, provider, messages, "model_budget_exhausted"
            )
        self._transition(state, AgentPhase.BUILD_TOOL_CONTEXT, request.budget)
        tools = self.tool_registry.expose(state)
        await self._emit_trace(request, AgentTraceEvent(
            kind="tools_available", run_id=state.run_id or state.request_id,
            run_version=state.run_version, sequence=self._trace_sequence(state),
            iteration=state.current_iteration,
            payload={"tools": [tool.name for tool in tools], "phase": state.phase.value},
        ))
        exposed_tool_names = frozenset(item.name for item in tools)
        if not tools and route.task_mode == "execute" and not state.tool_results:
            return self._failed(
                state,
                request,
                "No actionable tool is available for this route.",
                category="model_capability",
            )
        self._transition(state, AgentPhase.MODEL_STEP, request.budget)
        result = (
            LLMResult(content="", tool_calls=[LLMToolCall(
                id=f"catalog-page-{state.current_iteration}-{catalog_cursor}",
                name="discover_geospatial_capabilities",
                arguments={"cursor": catalog_cursor, "limit": 12},
            )]) if catalog_cursor is not None
            else await self._model_step(request, provider, messages, tools)
        )
        await self._emit_trace(request, AgentTraceEvent(
            kind="stage", run_id=state.run_id or state.request_id,
            run_version=state.run_version, sequence=self._trace_sequence(state),
            iteration=state.current_iteration,
            payload={"stage": "model_decision", "tool_names": [call.name for call in result.tool_calls],
                     "finish_reason": result.finish_reason, "model_calls": state.model_calls},
        ))
        if result.tool_calls:
            if catalog_cursor is None:
                messages.extend(self._assistant_and_tool_messages(result))
            tool_results = await self._execute_calls(
                request,
                result.tool_calls,
                state,
                exposed_tool_names=exposed_tool_names,
            )
            if await self._downgrade_unrenderable_route(
                request, route, tool_results
            ) or await self._revise_route(
                request, provider, messages, route, result.tool_calls, tool_results
            ):
                if catalog_cursor is None:
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
                self._sync_task_state(state)
                await self._checkpoint(request)
                await self._emit_iteration_completed(request, "continue")
                if iteration + 1 >= state.max_iterations:
                    final_text = await self._finalize_iteration_exhaustion(
                        request, provider, messages
                    )
                    return self._outcome(
                        state, final_text, "iteration_budget_exhausted", request
                    )
                return None
            location_map_recovery = await self._recover_location_only_map(
                request,
                route,
                state,
            )
            if not location_map_recovery and tool_results and all(
                item.status == "failed"
                and item.error is not None
                and item.error.error_type in {"tool_not_exposed", "unknown_tool"}
                for item in tool_results
            ):
                location_map_recovery = await self._recover_evidence_map(request, route, state)
            if location_map_recovery:
                # A successful location lookup is enough to complete a
                # location-only map contract.  Providers can otherwise keep
                # repeating the same lookup until the iteration budget is
                # exhausted instead of issuing the required map plan.
                tool_results.extend(location_map_recovery)
            self._ensure_run_control(request)
            if catalog_cursor is None:
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
            if any(item.tool_name not in _DERIVATION_TOOLS for item in tool_results):
                # New data or map work postdates the held-back answer.
                state.deferred_answer = None
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
                and route.task_mode == "execute"
                and state.prepared_map_session is None
                and data_verified_empty(state)
            ):
                # A completed empty query is the answer: nothing to map, rank or
                # compare, so say so instead of presenting empty data.
                final_text = await self._finalize_completed_request(
                    request, provider, messages
                )
                await self._emit_completion_decision(
                    request, reason="goal_satisfied", status="terminal"
                )
                state.termination_reason = "goal_satisfied"
                return self._outcome(state, final_text, "goal_satisfied", request)
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
            if await self._unproductive_step_detected(request, messages):
                final_text = await self._finalize_iteration_exhaustion(
                    request, provider, messages, stop_reason="no_progress"
                )
                # A stuck run that gathered results reports them as a limitation.
                reason = (
                    "insufficient_evidence"
                    if any(item.status == "success" for item in state.tool_results)
                    else "no_progress"
                )
                await self._emit_completion_decision(
                    request, reason=reason, status="terminal"
                )
                state.termination_reason = reason
                return self._outcome(state, final_text, reason, request)
            await self._emit_iteration_completed(request, "continue")
            if iteration + 1 >= state.max_iterations:
                final_text = await self._finalize_iteration_exhaustion(
                    request, provider, messages
                )
                return self._outcome(
                    state, final_text, "iteration_budget_exhausted", request
                )
            return None

        if not result.content.strip() and self._hit_output_limit(result):
            # Reasoning models can spend the whole output budget thinking and
            # return nothing; surface that instead of treating it as an answer.
            return self._failed(
                state,
                request,
                "The model used its entire output-token limit before producing "
                "an answer. Raise 'Max output tokens' in Settings, or choose a "
                "model that reasons less.",
                category="model_capability",
            )
        final_text = result.content.strip()
        target_results = await self._recover_route_target(request, state, tools)
        if target_results:
            # The text ignored a required lookup; it must not read as progress.
            final_text = ""
        recovery_results = (
            target_results
            or await self._recover_location_only_map(request, route, state)
            or await self._recover_evidence_map(request, route, state)
        )
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
                if final_text and not recovery_results:
                    state.deferred_answer = final_text
                return None
            if final_text and stop[0] not in {"awaiting_render", "clarification_required"}:
                checked = await self._verified_answer_text(
                    request, final_text, reason=stop[0]
                )
                if not checked:
                    final_text = (
                        self._evidence_findings(state)
                        or self._evidence_summary(state)
                        or (
                            self._verified_map_fallback(state)
                            if state.active_map_session is not None and state.render_verified
                            else ""
                        )
                        or "The model's answer did not match the verified results."
                    )
                    stop = (stop[0], final_text)
            if stop[0] == "no_progress" and final_text and not recovery_results:
                # The model keeps answering in text after every correction:
                # it has concluded no tool can close the gap.  Keep its
                # answer, disclose what is unmet, and do not call it a crash.
                stop = ("insufficient_evidence", self._limitation_disclosure(state, final_text))
                final_text = stop[1]
            elif stop[0] == "insufficient_evidence" and final_text:
                stop = (stop[0], self._limitation_disclosure(state, final_text))
                final_text = stop[1]
            await self._emit_completion_decision(
                request, reason=stop[0], status="terminal"
            )
            state.termination_reason = stop[0]
            return self._outcome(state, final_text, stop[0], request)
        if final_text:
            # An empty assistant turn carries nothing and nudges the model to repeat it.
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
        pending = self._pending_native_requirements(state)
        last = state.relevant_tool_outcomes[-1] if state.relevant_tool_outcomes else {}
        if (
            pending
            and state.no_progress_corrections
            and last.get("observation_type") == "pending_requirements"
            and last.get("pending_requirements") == pending
        ):
            # The model already got a correction naming exactly this gap and
            # still issued no tool call: a repeat only spends another full
            # context on the same answer.
            return False
        exposed = [
            tool.name
            for tool in self.tool_registry.expose(state, phase=AgentPhase.BUILD_TOOL_CONTEXT)
        ]
        derivable = bool(pending and state.evidence_refs) and all(
            _REQUIREMENT_TOOLS.get(name, frozenset()) & _DERIVATION_TOOLS & set(exposed)
            for name in pending
        )
        if derivable and state.no_progress_corrections:
            # The answer's evidence is already held: one targeted correction
            # names the derivation; past that the run finalizes from facts.
            return False
        state.no_progress_corrections += 1
        correction = self._no_progress_correction(state, exposed)
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
    async def _unproductive_step_detected(
        self,
        request: AgentLoopRequest,
        messages: list[dict[str, Any]],
    ) -> bool:
        """Track progress after a tool step; return True when the run is stuck.

        A step is productive when it establishes something the run has never
        held before.  Counting model or tool calls would treat busy loops as
        work, and comparing only with the previous step would miss cycles.
        """

        state = request.state
        signature = self._progress_signature(state)
        if signature not in state.progress_signatures:
            state.progress_signatures = [*state.progress_signatures, signature][-48:]
            state.unproductive_steps = 0
            return False
        state.unproductive_steps += 1
        limit = max(1, request.max_unproductive_steps)
        if state.unproductive_steps >= limit + 2:
            return True
        if state.unproductive_steps != limit:
            return False
        state.stuck_notices += 1
        notice = self._unproductive_notice(state, limit)
        state.relevant_tool_outcomes.append(notice)
        messages.append(
            {"role": "system", "content": json.dumps(notice, separators=(",", ":"))}
        )
        await self._emit_trace(
            request,
            AgentTraceEvent(
                kind="stage",
                run_id=state.run_id or state.request_id,
                run_version=state.run_version,
                sequence=self._trace_sequence(state),
                iteration=max(1, state.current_iteration),
                payload={
                    "stage": "no_progress_detected",
                    "unproductive_steps": state.unproductive_steps,
                    "recent_actions": notice["recent_actions"],
                },
            ),
        )
        return False

    # -------------------------------------------------------------------------
    @staticmethod
    def _progress_signature(state: AgentRunState) -> str:
        checks = AgentLoop._completion_checks(state)
        usable = [
            result
            for result in state.tool_results
            if result.status in {"success", "partial"}
        ]
        payload = {
            "locations": sorted(state.location_refs),
            "evidence": sorted(
                {
                    ref
                    for result in usable
                    if result.tool_name != "inspect_evidence"
                    for ref in result.evidence_refs
                }
            ),
            "inspected": sorted(
                {
                    ref
                    for result in usable
                    if result.tool_name == "inspect_evidence"
                    for ref in result.evidence_refs
                }
            ),
            "described": sorted(
                {
                    str(result.metadata.capability_id)
                    for result in usable
                    if result.tool_name == "describe_geospatial_capability"
                }
            ),
            "discovered": sorted(AgentLoop._discovered_entries(usable)),
            "capabilities": sorted(state.capability_ids),
            "excluded": sorted(state.excluded_capability_ids),
            "satisfied": sorted(name for name, value in checks.items() if value),
            "map": [
                state.prepared_map_session.session_id
                if state.prepared_map_session is not None
                else None,
                state.render_verified,
            ],
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    # -------------------------------------------------------------------------
    @staticmethod
    def _discovered_entries(results: list[ToolResult]) -> set[str]:
        entries: set[str] = set()
        for result in results:
            if result.tool_name != "discover_geospatial_capabilities":
                continue
            data = json_object(result.data)
            entries.add(f"cursor:{data.get('next_cursor')}")
            for key in ("capabilities", "items"):
                for item in json_array(data.get(key)):
                    record = json_object(item)
                    entries.add(str(record.get("id") or record.get("capability_id") or item))
        return entries

    # -------------------------------------------------------------------------
    def _unproductive_notice(self, state: AgentRunState, steps: int) -> dict[str, Any]:
        recent = state.tool_results[-6:]
        counts: dict[str, int] = {}
        for result in recent:
            counts[result.tool_name] = counts.get(result.tool_name, 0) + 1
        pending = self._pending_native_requirements(state)
        return {
            "observation_type": "no_progress_detected",
            "status": "action_required",
            "unproductive_steps": steps,
            "recent_actions": [
                {
                    "tool": result.tool_name,
                    "status": result.status,
                    "error_code": result.error.code if result.error else None,
                    "times_in_recent_steps": counts[result.tool_name],
                }
                for result in recent
            ],
            "still_missing": describe_requirements(pending) if pending else None,
            "tools_available": [tool.name for tool in self.tool_registry.expose(state)],
            "message": (
                f"The last {steps} tool steps established nothing new (no new "
                "place, usable data, capability, satisfied requirement or map). "
                "Do not repeat them. Use a different tool or different arguments; "
                "if no available tool can provide what is missing, answer now "
                "with what is known and say what is missing."
            ),
        }

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
        payload, redactions = redact_trace_value({
            "request_id": request.state.request_id,
            "conversation_id": request.state.conversation_id,
            "provider": request.provider, "model": request.model,
            **event.payload,
        })
        event = event.model_copy(update={
            "payload": payload, "redaction": {"fields": redactions, "raw_payload_omitted": True},
        })
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
    @staticmethod
    def _sanitize_finalization_candidate(content: str | None) -> tuple[str, bool]:
        """Suppress raw DSML protocol text returned as ordinary content."""

        candidate = (content or "").strip()
        if _DSML_MARKUP.search(candidate):
            return "", True
        return candidate, False

    # -------------------------------------------------------------------------
    async def _finalize_iteration_exhaustion(
        self,
        request: AgentLoopRequest,
        provider: AgentProvider,
        messages: list[dict[str, Any]],
        *,
        stop_reason: str = "iteration_budget_exhausted",
    ) -> str:
        """Make one bounded, tools-disabled finalization attempt.

        Exhaustion is a distinct terminal state even when the provider can
        provide a useful final explanation.  The model is never allowed to
        issue another tool call during this finalization step; unresolved
        server-owned obligations are appended deterministically so a polished
        but unsupported claim cannot be mistaken for completion.
        """

        state = request.state
        candidate = await self._verified_answer_text(
            request,
            await self._terminal_synthesis(
                request, provider, messages, reason="iteration_exhaustion"
            ),
            reason="iteration_exhaustion",
        )
        if not candidate:
            findings = self._evidence_findings(state)
            summary = self._evidence_summary(state)
            candidate = "\n\n".join(item for item in (findings, summary) if item)
        limit_label = _LIMIT_LABELS.get(stop_reason, "execution limit")
        pending = self._pending_requirements_for_task_state(state)
        if state.render_retry_exhausted:
            suffix = (
                "The map renderer did not produce a verified result after "
                f"{state.render_attempts} attempt(s); the previous map remains "
                "available."
            )
        elif pending:
            suffix = (
                f"The {limit_label} was reached before the request was complete: "
                + describe_requirements(pending)
                + "."
            )
        else:
            suffix = (
                f"The {limit_label} was reached before completion could be "
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
        candidate = await self._verified_answer_text(
            request,
            await self._terminal_synthesis(
                request, provider, messages, reason="verified_render"
            ),
            reason="verified_render",
        )
        final = (
            self._verified_map_state_summary(state)
            or candidate
            or self._verified_map_fallback(state)
        )
        notes = [
            item
            for item in (self._basemap_mismatch_note(state), self._empty_raster_note(state))
            if item
        ]
        return "\n\n".join([self._with_disclosure(state, final), *notes])

    # -------------------------------------------------------------------------
    @staticmethod
    def _empty_raster_note(state: AgentRunState) -> str | None:
        """Say so when a verified raster overlay drew nothing in the view."""

        session = state.prepared_map_session or state.active_map_session
        if session is None or not state.render_observations:
            return None
        empty = {
            item.get("capability_id")
            for item in state.render_observations[-1].overlay_results
            if item.get("raster_nontransparent_pixel_count") == 0
        }
        labels = [
            item.label
            for item in session.overlay_collection.instances
            if item.capability_id in empty
        ]
        if not labels:
            return None
        return f"Note: {', '.join(labels)} loaded, but it has no detections in the current view."

    # -------------------------------------------------------------------------
    def _basemap_mismatch_note(self, state: AgentRunState) -> str | None:
        """Disclose when the rendered basemap differs from the one the user named."""

        session = state.prepared_map_session or state.active_map_session
        if session is None:
            return None
        basemaps = self.capability_router.capability_registry.list_basemaps()
        requested = match_requested_basemaps(state.user_message, basemaps)
        labels = {str(item.get("id")): basemap_label(item) for item in basemaps}
        rendered = labels.get(session.basemap_id, session.basemap_id)
        if len(requested) > 1:
            named = " and ".join(labels.get(item, item) for item in requested)
            return (
                f"Note: you asked for {named}, but a map shows one basemap, "
                f"so it uses {rendered}."
            )
        unsupported = unsupported_basemap_styles(state.user_message)
        if unsupported and not requested:
            return (
                f"Note: {' '.join(unsupported)} basemaps are not available, so the "
                f"map uses {rendered}. Available basemaps: {', '.join(labels.values())}."
            )
        if not requested or requested[0] == session.basemap_id:
            return None
        return (
            f"Note: you asked for {labels.get(requested[0], requested[0])}, "
            f"but the map uses {rendered}."
        )

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
        framed = session.resolved_location.label
        # Name the place only when this request asked for it, not a view
        # carried over from an earlier turn.
        requested = framed and any(
            location_ref_matches(str(target), str(key), item.label)
            for target in route.target_refs
            for key, item in state.location_refs.items()
            if item.label == framed
        )
        summary = (
            "Map state update verified in the browser. "
            + (f"The map is framed on {framed}. " if requested else "")
            + f"Basemap: {basemap_label}. Visible overlays: {visible_text}."
        )
        if hidden:
            hidden_text = ", ".join(item for item in hidden if item)
            if hidden_text:
                summary += f" Hidden retained overlays: {hidden_text}."
        return summary

    # -------------------------------------------------------------------------
    @staticmethod
    def _verified_map_fallback(state: AgentRunState) -> str:
        """Name what the verified map shows when the model returned no text."""

        session = state.active_map_session
        if session is None:
            return "The map was updated and confirmed in the browser."
        places = [spellings[0] for spellings in resolved_route_target_names(state)]
        place = " and ".join(places) if places else session.resolved_location.label
        basemap = session.basemap or {}
        basemap_label = str(
            basemap.get("label") or basemap.get("name") or session.basemap_id
        ).strip()
        counts = map_layer_counts(state, session)
        layers = [
            label + _layer_count_text(counts.get(instance.instance_id))
            for instance in session.overlay_collection.instances
            if instance.visible and (label := str(instance.label or instance.capability_id).strip())
        ]
        marked = AgentLoop._marked_place_names(session)
        if marked:
            # A marking turn keeps the shown place; name what was added to it.
            text = f"Marked {len(marked)} place{'s' if len(marked) != 1 else ''} on the map: "
            return text + ", ".join(marked) + "."
        text = "The map now shows " + (place or "the requested area")
        text += f" on the {basemap_label} basemap" if basemap_label else ""
        text += f" with {', '.join(layers)}." if layers else "."
        identified = [
            value
            for item in AgentLoop.completion_summary(state).obligations
            if item.kind == "identification" and item.status == "met"
            for value in item.values
        ]
        if identified:
            text += f" Identified place: {'; '.join(identified)}."
        findings = AgentLoop._evidence_findings(state)
        return f"{text}\n\n{findings}" if findings else text

    # -------------------------------------------------------------------------
    @staticmethod
    def _marked_place_names(session: MapSession) -> list[str]:
        instance = next(
            (
                item
                for item in session.overlay_collection.instances
                if item.instance_id == PLACE_MARKERS_INSTANCE_ID and item.visible
            ),
            None,
        )
        if instance is None:
            return []
        features = json_array(json_object(instance.descriptor.get("data")).get("features"))
        return [
            name
            for feature in features
            if (name := str(json_object(json_object(feature).get("properties")).get("name") or "").strip())
        ]

    # -------------------------------------------------------------------------
    @staticmethod
    def _evidence_findings(state: AgentRunState) -> str:
        """List the leading derived records (name and values) of the run."""

        result = next(
            (
                item
                for item in reversed(state.tool_results)
                if item.tool_name == "transform_evidence"
                and item.status == "success"
                and isinstance(item.data, dict)
                and item.data.get("preview")
            ),
            None,
        )
        obligations = AgentLoop.completion_summary(state).obligations
        if any(item.kind == "location" and item.values for item in obligations):
            # A coordinate lookup's coordinates are its answer.
            return AgentLoop.completion_summary(state).value_lines()
        analysis = [item for item in obligations if item.kind == "analysis"]
        if analysis and (
            result is None or any(item.status != "met" or len(item.cite_groups) > 1 for item in analysis)
        ):
            # Records of an unfinished analysis are not its answer, nor are
            # leading fields the answer to a comparison: state the figures the
            # obligations delivered (disclosure names the rest).
            return AgentLoop.completion_summary(state).value_lines()
        if result is None:
            return AgentLoop._discovery_findings(state)
        metric = state.route.analysis.metric if state.route and state.route.analysis else None
        lines: list[str] = []
        for item in json_array(json_object(result.data).get("preview"))[:5]:
            record = json_object(item)
            values = json_object(record.get("properties")) or record
            label = str(
                values.get("place_label")
                or values.get("source_place")
                or values.get("name")
                or values.get("label")
                or ""
            ).strip()
            measures = [
                f"{key.replace('_', ' ')} {value:g}"
                for key, value in sorted(
                    values.items(), key=lambda pair: not key_names_variable(pair[0], metric)
                )
                if isinstance(value, (int, float))
                and not isinstance(value, bool)
                and key not in {"latitude", "longitude", "id", "time", "elevation"}
            ][:2]
            if label or measures:
                lines.append(f"- {label or 'record'}: {', '.join(measures)}".rstrip(": "))
        return "Top results:\n" + "\n".join(lines) if lines else ""

    # -------------------------------------------------------------------------
    @staticmethod
    def _forecast_values(result: ToolResult) -> str:
        """Range of each hourly variable a forecast result carries.

        A fallback answer that only says a forecast was returned does not
        answer the question it was fetched for.
        """

        data = json_object(result.data)
        rows = [json_object(row) for row in json_array(data.get("hourly_forecast"))]
        units = json_object(data.get("units"))
        parts: list[str] = []
        for name in dict.fromkeys(key for row in rows for key in row if key != "time"):
            values = [
                float(value) for row in rows
                if isinstance(value := row.get(name), (int, float)) and not isinstance(value, bool)
            ]
            if values:
                unit = units.get(name)
                suffix = f" {unit}" if isinstance(unit, str) else ""
                parts.append(f"{name.replace('_', ' ')} {min(values):g} to {max(values):g}{suffix}")
        window = ""
        if rows and data.get("forecast_window_start") and data.get("forecast_window_end"):
            window = f" between {data['forecast_window_start']} and {data['forecast_window_end']}"
        return f": {', '.join(parts[:8])}{window}" if parts else ""

    # -------------------------------------------------------------------------
    @staticmethod
    def _discovery_findings(state: AgentRunState) -> str:
        """List the sources a catalog-discovery question found.

        When the question is which data exists, the discovered capabilities
        are the answer; a resolved place alone never is.
        """

        if state.goal is None or state.goal.operation != "discover_available_map_data":
            return ""
        result = next(
            (
                item
                for item in reversed(state.tool_results)
                if item.tool_name == "discover_geospatial_capabilities"
                and item.status == "success"
            ),
            None,
        )
        if result is None:
            return ""
        lines = [
            f"- {entry.get('name') or entry.get('id')}: {str(entry.get('summary') or '').strip()}".rstrip(": ")
            for entry in (
                json_object(raw) for raw in json_array(json_object(result.data).get("capabilities"))[:8]
            )
        ]
        return "Available sources:\n" + "\n".join(lines) if lines else ""

    # -------------------------------------------------------------------------
    @staticmethod
    def completion_summary(state: AgentRunState) -> CompletionSummary:
        summary = build_completion_summary(state, AgentLoop._completion_checks(state))
        # Like the pending requirements, obligations are judged once the run's
        # tool context exists; an unhydrated state has verified nothing yet.
        if state.context_hydrated:
            return summary
        return summary.model_copy(update={"obligations": []})

    # -------------------------------------------------------------------------
    @staticmethod
    def _with_disclosure(state: AgentRunState, text: str) -> str:
        """Append what the user did not get, unless the text already says it."""

        summary = AgentLoop.completion_summary(state)
        lowered = text.casefold()
        summary.substitutions = [
            item for item in summary.substitutions
            if not (item[0].casefold() in lowered and item[2].casefold() in lowered)
        ]
        note = summary.disclosure()
        return f"{text.rstrip()}\n\n{note}" if note and note not in text else text

    # -------------------------------------------------------------------------
    async def _finalize_completed_request(
        self,
        request: AgentLoopRequest,
        provider: AgentProvider,
        messages: list[dict[str, Any]],
    ) -> str:
        """Synthesize a completed non-render request with tools disabled."""

        candidate = await self._reused_deferred_answer(request) or await self._verified_answer_text(
            request,
            await self._terminal_synthesis(
                request, provider, messages, reason="goal_satisfied"
            ),
            reason="goal_satisfied",
        )
        return self._with_disclosure(
            request.state,
            candidate
            or self._evidence_findings(request.state)
            or self._evidence_summary(request.state)
            or (
                self._verified_map_fallback(request.state)
                if request.state.active_map_session is not None and request.state.render_verified
                else ""
            )
            or "No answer could be produced from the available results.",
        )

    # -------------------------------------------------------------------------
    async def _terminal_synthesis(
        self,
        request: AgentLoopRequest,
        provider: AgentProvider,
        messages: list[dict[str, Any]],
        *,
        reason: str,
    ) -> str:
        """Make the run's single tools-disabled synthesis call.

        It may use the budget's one reserved model slot, so a run that spent
        its ordinary calls gathering evidence still gets a grounded answer.
        A provider violating ``tools=[]`` counts as an empty result.
        """

        state = request.state
        if state.finalization_attempted or request.budget.remaining_seconds() <= 0.001:
            await self._emit_finalization_trace(
                request,
                reason=reason,
                kind="finalization_completed",
                outcome=(
                    "already_attempted"
                    if state.finalization_attempted
                    else "budget_unavailable"
                ),
            )
            return ""
        state.finalization_attempted = True
        messages.append({
            "role": "system",
            "content": json.dumps(
                {
                    "observation_type": "completion_summary",
                    "instruction": (
                        "Answer only from this summary: disclose unmet obligations, "
                        "describe the map only if map_state is rendered, use given values."
                    ),
                    **self.completion_summary(state).model_view(),
                },
                separators=(",", ":"),
            ),
        })
        await self._emit_finalization_trace(
            request, reason=reason, kind="finalization_started"
        )
        candidate = ""
        outcome = "empty"
        try:
            for attempt in range(2):
                result = await self._model_step(
                    request, provider, messages, [], call_kind=TERMINAL_CALL_KIND
                )
                if result.tool_calls:
                    outcome = "tool_calls_suppressed"
                    break
                candidate, protocol_text_suppressed = (
                    self._sanitize_finalization_candidate(result.content)
                )
                outcome = (
                    "protocol_text_suppressed"
                    if protocol_text_suppressed
                    else "text"
                    if candidate
                    else "empty"
                )
                if outcome != "empty" or attempt:
                    break
                # One bounded correction: an empty answer answers nothing.
                messages.append({
                    "role": "system",
                    "content": json.dumps(
                        {
                            "observation_type": "empty_answer_correction",
                            "instruction": (
                                "Your answer was empty. Reply now in plain text, "
                                "answering the user's question from the evidence "
                                "and values already retrieved."
                            ),
                        },
                        separators=(",", ":"),
                    ),
                })
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
        except Exception as exc:
            log_unexpected_failure(
                LOGGER, exc, stage="finalization",
                run_id=request.state.run_id or request.state.request_id, reason=reason,
            )
            outcome = "error"
        finally:
            await self._emit_finalization_trace(
                request,
                reason=reason,
                kind="finalization_completed",
                outcome=outcome,
            )
        return candidate

    # -------------------------------------------------------------------------
    async def _verified_answer_text(
        self,
        request: AgentLoopRequest,
        candidate: str,
        *,
        reason: str,
    ) -> str:
        """Return ``candidate`` unless it contradicts the verified results.

        A contradicted answer is dropped (empty string) so the caller falls
        back to its deterministic text, and the violations are traced.
        """

        if not candidate.strip():
            return candidate
        candidate = drop_unsupported_time_zone_claims(
            candidate, evidence_utc_offsets(request.state)
        )
        violations = self._answer_violations(request.state, candidate)
        if not violations:
            return candidate
        if only_omissions(violations) and not any(
            item.kind in {"data", "analysis", "presentation"}
            for item in self.completion_summary(request.state).undelivered()
        ):
            # Nothing in the answer is false; it only leaves out what was not
            # delivered, so keep it and state the gap deterministically. With
            # data or the map undelivered, the text would describe what never
            # happened: invented values or an unchanged map.
            await self._emit_finalization_trace(
                request,
                reason=reason,
                kind="finalization_completed",
                outcome="disclosure_appended",
                violations=violations,
            )
            return self._with_disclosure(request.state, candidate)
        await self._emit_finalization_trace(
            request,
            reason=reason,
            kind="finalization_completed",
            outcome="answer_replaced",
            violations=violations,
            rejected_answer=candidate,
        )
        return ""

    # -------------------------------------------------------------------------
    async def _reused_deferred_answer(self, request: AgentLoopRequest) -> str:
        """Return the held-back text answer once derivation closed the contract.

        The model answered before deriving the figures; when only derivation
        over evidence it already saw followed, and the answer cites the derived
        values, a second full-context synthesis would only restate it.
        """

        state = request.state
        answer = state.deferred_answer or ""
        state.deferred_answer = None
        cited = any(
            item.kind == "analysis" and item.status == "met" and item.cite_groups
            for item in self.completion_summary(state).obligations
        )
        answer = drop_unsupported_time_zone_claims(answer, evidence_utc_offsets(state))
        if not answer.strip() or not cited or self._answer_violations(state, answer):
            return ""
        await self._emit_finalization_trace(
            request,
            reason="goal_satisfied",
            kind="finalization_completed",
            outcome="deferred_answer_reused",
        )
        return answer

    # -------------------------------------------------------------------------
    def _answer_violations(self, state: AgentRunState, candidate: str) -> list[str]:
        """Claims in ``candidate`` that the run's verified facts contradict."""

        session = state.active_map_session
        route = state.route
        visible = (
            [item for item in session.overlay_collection.instances if item.visible]
            if session is not None
            else []
        )
        targets = [loc.label for loc in state.location_refs.values() if loc.label]
        others = [
            item.resolved_location.label
            for item in visible
            if item.resolved_location is not None and item.resolved_location.label
        ]
        if session is not None and session.resolved_location.label:
            others.append(session.resolved_location.label)
        on_map = session is not None or (
            route is not None and route.presentation in {"map", "both"}
        )
        layers = len(visible) if on_map else None
        map_requested = route is not None and route.presentation in {"map", "both"}
        features: int | None = None
        if on_map:
            observation = state.render_observations[-1] if state.render_observations else None
            counts = [
                value
                for item in (observation.overlay_results if observation else [])
                if isinstance(value := item.get("rendered_feature_count"), int)
            ]
            # An earlier turn's empty map says nothing about a text answer's
            # "the two cities"; only a requested map is known to be empty.
            features = sum(counts) if counts else (0 if not visible and map_requested else None)
        summary = self.completion_summary(state)
        return check_final_answer(
            candidate,
            target_names=targets,
            other_places=others,
            layer_count=layers,
            feature_count=features,
            unmet=self._pending_native_requirements(state),
            unresolved_targets=unresolved_route_targets(state),
            required_targets=[
                *resolved_route_target_names(state),
                *(
                    item.answer_must_name
                    for item in summary.obligations
                    if item.answer_must_name
                ),
            ],
            undelivered=[item.label or item.obligation_id for item in summary.undelivered()],
            map_rendered=(
                False
                if summary.map_state == "failed"
                or (map_requested and summary.map_state == "none")
                else None
            ),
            evidence_numbers=evidence_numbers(state),
            truncations=summary.truncations,
            layer_edits=layer_edit_count(state) if on_map else None,
            cite_groups=[
                group
                for item in summary.obligations
                if item.kind in {"analysis", "location"} and item.status == "met"
                for group in item.cite_groups
            ],
            coordinates=[
                *(
                    value
                    for location in state.location_refs.values()
                    for value in (location.latitude, location.longitude)
                ),
                *evidence_coordinates(state),
            ],
            prior_numbers=prior_evidence_numbers(state),
            render_settled=state.render_verified,
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def _evidence_summary(state: AgentRunState) -> str:
        """List what the run established when no model synthesis is available."""

        lines = [
            f"- {result.summary.strip()}"
            + (
                f" (source: {result.metadata.provider_id})"
                if result.metadata.provider_id
                else ""
            )
            + AgentLoop._forecast_values(result)
            for result in state.tool_results
            if result.status in {"success", "partial", "valid_empty"}
            and result.tool_name in _EVIDENCE_TOOLS
            and result.summary.strip()
            and not (needs_numeric_values(state) and result.metadata.result_type == "raster")
        ]
        if not lines:
            return ""
        return "Results gathered so far:\n" + "\n".join(lines[-8:])

    # -------------------------------------------------------------------------
    async def _emit_finalization_trace(
        self,
        request: AgentLoopRequest,
        *,
        reason: str,
        kind: Literal["finalization_started", "finalization_completed"],
        outcome: str | None = None,
        violations: list[str] | None = None,
        rejected_answer: str | None = None,
    ) -> None:
        """Expose the tools-disabled finalization boundary.

        The only content is an answer the gate rejected, which no other record
        keeps and which replaying a gate decision needs.
        """

        state = request.state
        payload: dict[str, Any] = {
            "reason": reason,
            "tools_exposed": 0,
            "tool_choice": "none",
            "model_call_index": state.model_calls,
        }
        if outcome is not None:
            payload["outcome"] = outcome
        if violations:
            payload["final_answer_violations"] = violations
        if rejected_answer is not None:
            payload["rejected_answer"] = rejected_answer
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
                "max_iterations": max(1, int(max_iterations)),
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
        goal = state.goal
        target_ids = list(goal.target_ids) if goal is not None else []
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
            obligations=list(goal.obligations) if goal is not None else [],
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
        if requested_transform_unmet(state):
            required.append("requested_transform_applied")
        return [name for name in required if not checks.get(name, False)]

    # -------------------------------------------------------------------------
    @staticmethod
    def _completion_checks(state: AgentRunState) -> dict[str, bool]:
        evidence_checks = CompletionEvaluator.data_checks(state)
        completed_data = evidence_checks["required_data_retrieved"]
        discovery_results = [
            result
            for result in state.tool_results
            if result.tool_name == "discover_geospatial_capabilities"
        ]
        catalog_discovery_only = (
            state.goal is not None
            and state.goal.operation == "discover_available_map_data"
            and state.goal.presentation == "text"
        )
        if catalog_discovery_only:
            latest_discovery = discovery_results[-1] if discovery_results else None
            latest_data = (
                latest_discovery.data
                if latest_discovery is not None
                and isinstance(latest_discovery.data, dict)
                else None
            )
            capabilities_discovered = bool(
                latest_discovery is not None
                and latest_discovery.status in {"success", "valid_empty"}
                and latest_data is not None
                and "next_cursor" in latest_data
                and latest_data.get("next_cursor") is None
            )
        else:
            capabilities_discovered = any(
                result.status in {"success", "valid_empty"}
                for result in discovery_results
            )
        geocode_location_resolved = (
            is_text_location_lookup(state.route)
            and bool(state.location_refs)
            and any(
                result.tool_name == "resolve_geospatial_location"
                and result.status == "success"
                for result in state.tool_results
            )
        )
        evidence_inspected = any(
            result.tool_name == "inspect_evidence"
            and result.status in {"success", "valid_empty"}
            for result in state.tool_results
        )
        data_completed = completed_data or geocode_location_resolved
        # Without required evidence there is no provider request a scope could
        # be applied to; the map candidate's own layers carry the scope check.
        map_scope_applied = not (
            state.completion_contract and state.completion_contract.evidence_required
        ) and (
            state.prepared_map_session is not None
            or (state.active_map_session is not None and state.render_verified)
        )
        return {
            "location_resolved": route_target_location_available(state),
            "search_area_bound": route_target_location_available(state),
            "result_locations_derived": analysis_complete(state),
            "measurement_computed": any(
                result.tool_name == "measure_geospatial" and result.status == "success"
                for result in state.tool_results
            ),
            "required_data_retrieved": data_completed,
            "evidence_inspected": evidence_inspected,
            "capabilities_discovered": capabilities_discovered,
            "temporal_scope_applied": evidence_checks["temporal_scope_applied"]
            or map_scope_applied,
            # A successful map-plan observation is the server-owned proof
            # that the requested spatial scope was applied.  Location-only
            # map requests have no data tool result, so using ``completed_data``
            # alone left their spatial task pending even after a valid
            # candidate had been prepared.
            "spatial_scope_applied": evidence_checks["spatial_scope_applied"]
            or geocode_location_resolved
            or map_scope_applied,
            "map_candidate_prepared": state.prepared_map_session is not None
            or (state.active_map_session is not None and state.render_verified),
            "render_verified": bool(state.render_verified),
            "requested_transform_applied": not requested_transform_unmet(state),
            "locations_marked": not unmarked_route_targets(state),
        }

    # -------------------------------------------------------------------------
    @staticmethod
    def _pending_catalog_discovery_cursor(state: AgentRunState) -> str | None:
        """Return the next catalog page cursor for a discovery-only route."""

        if (
            state.goal is None
            or state.goal.operation != "discover_available_map_data"
        ):
            return None
        latest = next(
            (
                result
                for result in reversed(state.tool_results)
                if result.tool_name == "discover_geospatial_capabilities"
            ),
            None,
        )
        if latest is None or latest.status != "success" or not isinstance(latest.data, dict):
            return None
        cursor = latest.data.get("next_cursor")
        return str(cursor).strip() if cursor is not None and str(cursor).strip() else None

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
            "search_area_bound": "location",
            "result_locations_derived": "evidence_analysis",
            "measurement_computed": "evidence_analysis",
            "capabilities_discovered": "capability_discovery",
            "required_data_retrieved": "provider_data",
            "evidence_inspected": "evidence_inspection",
            "temporal_scope_applied": "temporal_scope",
            "spatial_scope_applied": "spatial_scope",
            "map_candidate_prepared": "map_candidate",
            "locations_marked": "map_candidate",
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
        revision: dict[str, object] | None = None,
    ) -> tuple[str | None, str, CapabilityRoute | None]:
        registered_route_tool = self.tool_registry.get("route_request")
        if registered_route_tool is None:
            return "Routing is unavailable for this request.", "provider_error", None
        route_tool = registered_route_tool.definition
        # The route call has its own instructions; the native tool-loop prompt
        # describes tools this call cannot use and would contradict them.
        native_prompt = build_native_agent_system_prompt()
        correction_messages = [
            {"role": "system", "content": build_capability_route_prompt()},
            {
                "role": "system",
                "content": "Current time: "
                + datetime.now(UTC).replace(microsecond=0).isoformat()
                + " (UTC).",
            },
            *(
                message
                for message in messages
                if message.get("content") != native_prompt
                # The routing call exposes only route_request: tool-call
                # history (and an assistant call whose results are not yet
                # appended) is a malformed request for chat-completion APIs.
                and not (
                    revision is not None
                    and (message.get("role") == "tool" or message.get("tool_calls"))
                )
            ),
        ]
        if revision is not None:
            correction_messages.append(
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "route_revision": True,
                            "instruction": (
                                "The previous route could not run the requested "
                                "operation. Return one route_request call for the "
                                "latest user request whose domain exposes the tools "
                                "that operation needs; filtering or transforming data "
                                "is not a map-state change."
                            ),
                            # An obligation violation names its own instruction.
                            **revision,
                        },
                        separators=(",", ":"),
                    ),
                }
            )
        result: LLMResult | None = None
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
            validation_errors: list[dict[str, str]] = []
            if (
                call is not None
                and call.name == route_tool.name
                and call.parse_error is None
                and call.arguments is not None
            ):
                try:
                    proposed = CapabilityRoute.model_validate(call.arguments)
                except ValidationError as exc:
                    proposed = (
                        self._salvage_route(call.arguments, exc)
                        if attempt == request.max_route_corrections
                        else None
                    )
                    validation_errors = [
                        {
                            "field": ".".join(str(part) for part in error["loc"])
                            or "(root)",
                            "message": error["msg"],
                        }
                        for error in exc.errors()[:8]
                    ]
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
                        request.state.clarification_options = list(
                            decision.clarification_options
                        )
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
                    "content": (
                        json.dumps(
                            {
                                "route_invalid": True,
                                "errors": validation_errors,
                                "instruction": (
                                    "Return one corrected route_request call "
                                    "matching the supplied schema."
                                ),
                            },
                            separators=(",", ":"),
                        )
                        if validation_errors
                        else self._route_missing_call_instruction(call, route_tool.name)
                    ),
                }
            )
        fallback = build_location_map_fallback_route(request.state.user_message)
        if (
            fallback is None
            and result is not None
            and not result.tool_calls
            and (result.content or "").strip()
        ):
            # The model answered in plain text instead of calling route_request.
            fallback = build_conversation_fallback_route()
        if fallback is not None:
            decision = self.capability_router.validate_route(
                fallback,
                user_message=request.state.user_message,
                active_state=request.state,
            )
            if decision.status in {"accepted", "discovery_required"}:
                request.state.capability_ids = list(decision.capability_ids)
                request.state.route_source = "fallback"
                return None, "", decision.route
        return None, "", None

    # -------------------------------------------------------------------------
    @staticmethod
    def _route_mismatch(
        route: CapabilityRoute, results: list[ToolResult]
    ) -> str | None:
        """Name concrete evidence that the route cannot express the request.

        A data tool the route's domain does not expose shows a wrong
        interpretation; argument errors and capability replans are the
        model's and the recovery loop's to handle and never revise the route.
        """

        for result in results:
            if (
                result.status == "failed"
                and result.error is not None
                and result.tool_name in _ROUTE_DATA_TOOLS
                and result.error.error_type == "tool_not_exposed"
            ):
                return f"{result.tool_name}_unavailable_for_{route.primary_domain.value}_route"
        return None

    # -------------------------------------------------------------------------
    @staticmethod
    def _obligation_violation(
        state: AgentRunState,
    ) -> tuple[str, list[RequestObligation]] | None:
        """Check the compiled goal against the request before any tool runs.

        Every required obligation must map to the route, and a place already
        resolved in this conversation that the user names again must be one
        of the route's targets.  Returns a reason code with the obligations it
        concerns, or None when the route can carry the whole request.
        """

        goal = state.goal
        route = state.route
        if goal is None or route is None or goal.task_mode != "execute":
            return None
        violation = unrouted_obligations(goal, state.completion_requirements)
        if violation is not None or route.location_mode != "target" or not goal.target_ids:
            return violation
        omitted: list[RequestObligation] = []
        for key, name in places_named_in(state.user_message, state.location_refs):
            location = state.location_refs[key]
            normalized = normalize_target_key(name)
            if any(
                location_ref_matches(target, key, location.label)
                or same_target(target, name)
                or f" {normalized} " in f" {normalize_target_key(target)} "
                for target in goal.target_ids
            ):
                continue
            omitted.append(
                RequestObligation(
                    id=f"location:{normalized.replace(' ', '-')}"[:200],
                    kind="location",
                    target_ids=[name],
                )
            )
        if omitted:
            return "known_place_missing_from_targets", omitted[:16]
        # "Remove that layer": an earlier turn's data subject is not a place.
        subjects = {
            normalize_target_key(item.variable)
            for item in state.prior_tasks
            if item.kind == "data" and item.variable
        }
        misread = [
            RequestObligation(id=f"location:{normalize_target_key(target).replace(' ', '-')}"[:200], kind="location", target_ids=[target])
            for target in goal.target_ids
            if normalize_target_key(target) in subjects
            and not any(location_ref_matches(target, str(key), item.label) for key, item in state.location_refs.items())
        ]
        if misread:
            return "prior_subject_used_as_place", misread[:16]
        return None

    # -------------------------------------------------------------------------
    async def _downgrade_unrenderable_route(
        self,
        request: AgentLoopRequest,
        route: CapabilityRoute,
        results: list[ToolResult],
    ) -> bool:
        """Answer in text when only non-rendering sources match a text-and-map route.

        Discovery names the sources that match once map rendering is relaxed.
        For a ``both`` route the text answer is still wanted, so the route drops
        to ``text`` and those sources become selectable; a ``map`` route keeps
        its rendering requirement.
        """

        state = request.state
        if route.presentation != "both" or state.route is not route:
            return False
        alternatives: list[str] = []
        for result in results:
            if result.tool_name != "discover_geospatial_capabilities":
                continue
            diagnostics = json_object(json_object(result.data).get("diagnostics"))
            for item in json_array(diagnostics.get("unmet_constraints")):
                unmet = json_object(item)
                if unmet.get("constraint") != "map_rendering":
                    continue
                for entry in json_array(unmet.get("alternatives")):
                    identifier = json_object(entry).get("id")
                    if identifier:
                        alternatives.append(str(identifier))
        if not alternatives:
            return False
        previous = route.model_dump(mode="json", exclude_defaults=True)
        revised = route.model_copy(update={"presentation": "text"})
        state.route = revised
        previous_contract = state.completion_contract
        self._compile_native_goal(
            state,
            revised,
            requests_entities=self.capability_router.requests_catalog_entities(
                state.user_message
            ),
            servable_queries=self.capability_router.capability_registry.servable_queries,
        )
        self._keep_data_obligation(state, previous_contract)
        state.capability_ids = list(dict.fromkeys([*state.capability_ids, *alternatives]))[:12]
        await self._emit_trace(
            request,
            AgentTraceEvent(
                kind="plan_revised",
                run_id=state.run_id or state.request_id,
                run_version=state.run_version,
                sequence=self._trace_sequence(state),
                iteration=max(1, state.current_iteration),
                payload={
                    "reason": "text_only_capability_available",
                    "previous_route": previous,
                    "outcome": "revised",
                },
            ),
        )
        return True

    # -------------------------------------------------------------------------
    async def _revise_route(
        self,
        request: AgentLoopRequest,
        provider: AgentProvider,
        messages: list[dict[str, Any]],
        route: CapabilityRoute,
        calls: list[LLMToolCall],
        results: list[ToolResult],
        *,
        reason: str | None = None,
        missing: list[RequestObligation] | None = None,
    ) -> bool:
        """Revise the route once per run when it cannot express the request.

        The reason is either a tool result that showed the route was wrong or
        a pre-tool obligation violation (``reason`` with the ``missing``
        obligations).  Completed evidence stays in the run state; only the
        route, goal and contract are recompiled.  A revision that drops a
        required obligation of the prior goal is rejected and the prior route
        stays.  Every attempt is traced old to new.
        """

        state = request.state
        reason = reason or self._route_mismatch(route, results)
        if reason is None or state.route_revisions:
            return False
        previous = route.model_dump(mode="json", exclude_defaults=True)
        # Recorded before the call so a failed attempt is never retried.
        record: dict[str, object] = {"reason": reason, "previous_route": previous}
        revision: dict[str, object] = {"reason": reason, "previous_route": previous}
        if missing:
            record["missing_obligations"] = [item.id for item in missing]
            revision["missing_obligations"] = [
                item.model_dump(mode="json", exclude_defaults=True) for item in missing
            ]
            revision["instruction"] = (
                "The target_refs in missing_obligations name the data subject of an "
                "earlier request, not a place. Return one route_request call whose "
                "target_refs are only the places the latest user message asks for; "
                "existing map layers are edited through the map state."
                if reason == "prior_subject_used_as_place"
                else "The previous route does not cover every part of the latest user "
                "request listed in missing_obligations. Return one route_request "
                "call whose target_refs, domains, analysis and presentation cover "
                "all of them, and list every part in obligations."
            )
        state.route_revisions.append(record)
        # Routing may replace the shortlist; a rejected revision restores it.
        prior_capability_ids = list(state.capability_ids)
        prior_route_source = state.route_source
        try:
            _, _, revised = await self._route(
                request,
                provider,
                messages,
                revision=revision,
            )
        except (AgentRunControlSignal, asyncio.CancelledError, ExecutionBudgetExceeded):
            raise
        except LLMProviderRequestError as exc:
            if exc.timeout_origin == "application_deadline":
                raise
            return await self._revision_failed(request, record, exc.code or type(exc).__name__)
        except Exception as exc:
            # The revision is an optional repair; the original route stands.
            return await self._revision_failed(
                request, record, f"{type(exc).__name__}: {str(exc)[:160]}"
            )
        if revised is None:
            record["outcome"] = "unchanged"
            return False
        prior = (
            state.route,
            state.goal,
            state.completion_contract,
            list(state.completion_requirements),
            dict(state.task_state),
        )
        prior_obligations = list(state.goal.obligations) if state.goal is not None else []
        if reason == "prior_subject_used_as_place":
            # The misread targets were never part of the request.
            misread = {target for item in missing or [] for target in item.target_ids}
            prior_obligations = [
                item.model_copy(update={"target_ids": [t for t in item.target_ids if t not in misread]})
                for item in prior_obligations
                if not (item.kind == "location" and set(item.target_ids) <= misread)
            ]
        state.route = revised
        self._compile_native_goal(
            state,
            revised,
            requests_entities=self.capability_router.requests_catalog_entities(
                state.user_message
            ),
            servable_queries=self.capability_router.capability_registry.servable_queries,
        )
        record["revised_route"] = revised.model_dump(mode="json", exclude_defaults=True)
        dropped = dropped_obligations(
            prior_obligations, state.goal.obligations if state.goal is not None else []
        )
        if dropped:
            # A revision repairs how the request is routed, never what it asks.
            (
                state.route,
                state.goal,
                state.completion_contract,
                state.completion_requirements,
                state.task_state,
            ) = prior
            state.capability_ids = prior_capability_ids
            state.route_source = prior_route_source
            record["outcome"] = "rejected"
            record["dropped_obligations"] = [item.id for item in dropped]
            await self._emit_trace(
                request,
                AgentTraceEvent(
                    kind="plan_revised",
                    run_id=state.run_id or state.request_id,
                    run_version=state.run_version,
                    sequence=self._trace_sequence(state),
                    iteration=max(1, state.current_iteration),
                    payload=dict(record),
                ),
            )
            return False
        self._forgive_route_rejections(state, calls, results)
        self._bind_search_area(state, revised)
        record["outcome"] = "revised"
        await self._refresh_capabilities_after_location(request, state, [])
        await self._emit_trace(
            request,
            AgentTraceEvent(
                kind="plan_revised",
                run_id=state.run_id or state.request_id,
                run_version=state.run_version,
                sequence=self._trace_sequence(state),
                iteration=max(1, state.current_iteration),
                payload=dict(record),
            ),
        )
        return True

    # -------------------------------------------------------------------------
    @staticmethod
    def _keep_data_obligation(
        state: AgentRunState, previous: CompletionContract | None
    ) -> None:
        """Never let a route revision drop the provider-data obligation.

        A revision repairs how the request is routed, not what it asks for; a
        revised route that cannot execute capabilities would otherwise let a
        bare location fit satisfy a request for data.
        """

        contract = state.completion_contract
        if (
            previous is None
            or contract is None
            or "required_data_retrieved" not in previous.requirements
            or "required_data_retrieved" in contract.requirements
        ):
            return
        state.completion_requirements = list(
            dict.fromkeys([*state.completion_requirements, "required_data_retrieved"])
        )
        state.completion_contract = contract.model_copy(
            update={
                "requirements": list(state.completion_requirements),
                "data_requirement": previous.data_requirement,
                "evidence_required": True,
                "data_obligations": list(previous.data_obligations),
            }
        )

    # -------------------------------------------------------------------------
    def _forgive_route_rejections(
        self,
        state: AgentRunState,
        calls: list[LLMToolCall],
        results: list[ToolResult],
    ) -> None:
        """Do not charge the revised route for calls the old route rejected.

        A tool the old route did not expose says the route was wrong, not the
        model.  The batch that triggered the revision is removed from the
        correction, consecutive-failure and repeat counters so the model
        starts the revised route with its full budget.
        """

        rejected = [
            call
            for call, result in zip(calls, results, strict=False)
            if result.status == "failed"
            and result.error is not None
            and result.error.error_type == "tool_not_exposed"
        ]
        for call in rejected:
            fingerprint = self._fingerprint(call)
            remaining = state.failed_fingerprints.get(fingerprint, 0) - 1
            if remaining > 0:
                state.failed_fingerprints[fingerprint] = remaining
            else:
                state.failed_fingerprints.pop(fingerprint, None)
        if rejected and all(result.status == "failed" for result in results):
            state.validation_corrections = max(0, state.validation_corrections - 1)
            state.consecutive_tool_failures = max(
                0, state.consecutive_tool_failures - 1
            )

    # -------------------------------------------------------------------------
    async def _revision_failed(
        self, request: AgentLoopRequest, record: dict[str, object], reason: str
    ) -> bool:
        """Record a failed revision call and let the run continue on its route."""

        state = request.state
        record["outcome"] = "failed"
        record["failure_reason"] = redact_trace_value(reason[:200])[0]
        await self._emit_trace(
            request,
            AgentTraceEvent(
                kind="plan_revised",
                run_id=state.run_id or state.request_id,
                run_version=state.run_version,
                sequence=self._trace_sequence(state),
                iteration=max(1, state.current_iteration),
                payload=dict(record),
            ),
        )
        return False

    # -------------------------------------------------------------------------
    def _fast_route(
        self, request: AgentLoopRequest
    ) -> tuple[None, str, CapabilityRoute] | None:
        """Skip the routing call for an unequivocal single-place display."""

        state = request.state
        capture_store = getattr(self, "capture_store", None)
        if capture_store is not None and capture_store.attachment_for_run(
            state.run_id or state.request_id
        ) is not None:
            return None
        proposed = self.capability_router.fast_route(state.user_message)
        if proposed is None:
            return None
        decision = self.capability_router.validate_route(
            proposed,
            user_message=state.user_message,
            active_state=state,
        )
        if decision.status not in {"accepted", "discovery_required"}:
            return None
        state.capability_ids = list(decision.capability_ids)
        state.route_source = "fast"
        return None, "", decision.route

    # -------------------------------------------------------------------------
    @staticmethod
    def _route_missing_call_instruction(call: Any, tool_name: str) -> str:
        if call is None:
            problem = f"No tool call was returned; reply only by calling {tool_name}."
        elif call.name != tool_name:
            problem = f"Unexpected tool {call.name}; call only {tool_name}."
        elif call.parse_error is not None:
            problem = f"The {tool_name} arguments were not valid JSON."
        else:
            problem = f"The {tool_name} call had no arguments."
        return f"{problem} Return one valid {tool_name} call matching the supplied schema."

    # -------------------------------------------------------------------------
    @staticmethod
    def _salvage_route(
        arguments: dict[str, Any], error: ValidationError
    ) -> CapabilityRoute | None:
        """Drop invalid optional route fields; required fields are never guessed.

        The one implied value is ``task_mode``: answer and clarify routes cannot
        present a map, so a map route that omits it can only execute.
        """

        if "task_mode" not in arguments and arguments.get("presentation") in {"map", "both"}:
            arguments = {**arguments, "task_mode": "execute"}
            try:
                return CapabilityRoute.model_validate(arguments)
            except ValidationError as exc:
                error = exc
        fields = CapabilityRoute.model_fields
        invalid = {str(item["loc"][0]) for item in error.errors() if item["loc"]}
        if not invalid or any(
            name in fields and fields[name].is_required() for name in invalid
        ):
            return None
        try:
            return CapabilityRoute.model_validate(
                {key: value for key, value in arguments.items() if key not in invalid}
            )
        except ValidationError:
            return None

    # -------------------------------------------------------------------------
    async def _model_step(
        self,
        request: AgentLoopRequest,
        provider: AgentProvider,
        messages: list[dict[str, Any]],
        tools: list[LLMToolDefinition],
        *,
        call_kind: str = ITERATION_CALL_KIND,
    ) -> LLMResult:
        working = self._working_state_message(request.state, request.max_tool_result_chars)
        model_messages = [
            *self._model_context_messages(request, messages),
            {"role": "system", "content": working},
        ]
        model_messages = await self._attach_vision_capture(
            request,
            provider,
            model_messages,
            call_kind=call_kind,
        )
        return await self._model_call(
            request,
            provider,
            model_messages,
            tools,
            tool_choice="auto" if tools else "none",
            terminal=call_kind == TERMINAL_CALL_KIND,
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def _hit_output_limit(result: LLMResult) -> bool:
        reason = (result.finish_reason or "").strip().lower()
        return reason in {"length", "max_tokens", "max_output_tokens"}

    # -------------------------------------------------------------------------
    async def _attach_vision_capture(
        self,
        request: AgentLoopRequest,
        provider: AgentProvider,
        model_messages: list[dict[str, Any]],
        *,
        call_kind: str,
    ) -> list[dict[str, Any]]:
        """Attach a captured map image when the vision policy allows it.

        Vision degrades cleanly: a missing/unsupported capability, a missing
        capture, or an exhausted vision budget simply leaves the messages
        unchanged and records a trace event.  This never alters retry counts
        or budgets.
        """

        state = request.state
        capture_store = getattr(self, "capture_store", None)
        if capture_store is None:
            return model_messages
        supports_vision = (
            provider.supports_vision(request.model)
            if hasattr(provider, "supports_vision")
            else None
        )
        engine = VisionPolicyEngine(
            policy=request.vision_policy,
            vision_supported=supports_vision,
            max_vision_calls=request.vision_max_calls,
        )
        capture_ref = engine.current_capture_ref(state)
        capture = None
        if capture_ref and self._is_capture_identity(capture_ref):
            map_session_id, collection_revision = self._split_capture_identity(
                capture_ref
            )
            capture = capture_store.get(
                request.state.run_id or request.state.request_id,
                map_session_id,
                collection_revision,
            )
        # Judge the policy as if the capture existed, so ``capture_missing``
        # is recorded only when an image was wanted but never arrived.
        if capture_ref is None or not engine.should_attach(
            state,
            capture_ref=capture_ref,
            capture_present=True,
            call_kind=call_kind,
        ):
            return model_messages
        if capture is None:
            if call_kind == TERMINAL_CALL_KIND:
                await self._emit_vision_trace(request, "capture_missing", capture_ref)
            return model_messages
        caption = self._vision_caption(state, capture_ref)
        model_messages = attach_image(
            model_messages,
            data=capture.image_base64,
            mime_type=capture.mime_type,
            caption=caption,
        )
        engine.mark_attached(state, capture_ref=capture_ref)
        await self._emit_vision_trace(
            request,
            "vision_attached",
            capture_ref,
            {
                "mime_type": capture.mime_type,
                "width": capture.width,
                "height": capture.height,
                "call_kind": call_kind,
                "vision_calls": (
                    state.vision_state.vision_calls if state.vision_state else 0
                ),
            },
        )
        return model_messages

    # -------------------------------------------------------------------------
    @staticmethod
    def _is_capture_identity(value: str) -> bool:
        return value.count(":") == 1

    # -------------------------------------------------------------------------
    @staticmethod
    def _split_capture_identity(value: str) -> tuple[str, int]:
        map_session_id, _, revision = value.partition(":")
        return map_session_id, int(revision)

    # -------------------------------------------------------------------------
    @staticmethod
    def _vision_caption(state: AgentRunState, capture_ref: str) -> str:
        """Concise caption telling the model what the image represents."""

        # The candidate is cleared at acknowledgement, so the capture shows the
        # session that was just committed.
        session = state.prepared_map_session or state.active_map_session
        basemap_id = ""
        overlay_count = 0
        if session is not None:
            basemap_id = str(session.basemap_id or "")
            overlay_count = len(session.overlay_collection.instances)
        return (
            "This is a capture of the map rendered by the agent for this request "
            f"(render {capture_ref}). "
            f"Basemap: {basemap_id or 'default'}; overlay count: {overlay_count}. "
            "Inspect the rendered map directly for anything the structured "
            "state does not capture."
        )

    # -------------------------------------------------------------------------
    async def _attach_user_image(
        self,
        request: AgentLoopRequest,
        provider: AgentProvider,
        messages: list[dict[str, Any]],
        *,
        first_call: bool,
    ) -> list[dict[str, Any]]:
        """Give every model call of the run the image the user attached.

        Independent of the map-capture vision policy: the image is part of the
        request itself. A model without vision gets a note instead, so it can
        tell the user rather than guess.
        """

        capture_store = getattr(self, "capture_store", None)
        if capture_store is None:
            return messages
        attachment = capture_store.attachment_for_run(
            request.state.run_id or request.state.request_id
        )
        if attachment is None:
            return messages
        supported = (
            provider.supports_vision(request.model)
            if hasattr(provider, "supports_vision")
            else None
        )
        if supported is not True:
            if first_call:
                await self._emit_vision_trace(request, "user_image_unsupported", None)
            return [*messages, {"role": "system", "content": USER_IMAGE_UNSUPPORTED_NOTE}]
        if first_call:
            await self._emit_vision_trace(
                request,
                "user_image_attached",
                None,
                {"mime_type": attachment.mime_type, "width": attachment.width, "height": attachment.height},
            )
        return attach_image(
            messages,
            data=attachment.image_base64,
            mime_type=attachment.mime_type,
            caption=USER_IMAGE_CAPTION,
        )

    # -------------------------------------------------------------------------
    async def _emit_vision_trace(
        self,
        request: AgentLoopRequest,
        kind: TraceKind,
        capture_ref: str | None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        state = request.state
        payload: dict[str, Any] = {"capture_ref": capture_ref}
        if extra:
            payload.update(extra)
        await self._emit_trace(
            request,
            AgentTraceEvent(
                kind=kind,
                run_id=state.run_id or state.request_id,
                run_version=max(1, int(state.run_version or 1)),
                sequence=self._trace_sequence(state),
                iteration=state.current_iteration if state.current_iteration > 0 else None,
                payload=payload,
            ),
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
        protocol_messages = self._protocol_messages(messages)
        if not protocol_messages and state.provider_continuation:
            protocol_messages = self._protocol_messages(
                [dict(item) for item in state.provider_continuation]
            )
        # A result whose tool message is still in the protocol window is
        # already model-visible; repeat only results the window trimmed.
        answered = self._protocol_result_call_ids(protocol_messages)
        observations = [
            ModelObservation.from_tool_result(
                result,
                max_chars=min(request.max_tool_result_chars, 2048),
            ).model_dump(mode="json", exclude_none=True)
            for result in state.tool_results[-8:]
            if result.call_id not in answered
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
        return [*context, *protocol_messages]

    # -------------------------------------------------------------------------
    @staticmethod
    def _protocol_result_call_ids(messages: list[dict[str, Any]]) -> set[str]:
        ids: set[str] = set()
        for message in messages:
            if message.get("role") == "tool":
                value = message.get("tool_call_id")
            elif message.get("type") == "function_call_output":
                value = message.get("call_id")
            else:
                continue
            if isinstance(value, str) and value:
                ids.add(value)
        return ids

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
        if any(message.get("google_content") for message in protocol):
            # Gemini validates every signature in the current tool-calling
            # turn. Run iteration/tool budgets bound this history; slicing a
            # window would discard required sequential continuation state.
            return protocol
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
        terminal: bool = False,
    ) -> LLMResult:
        self._ensure_run_control(request)
        request.budget.ensure_available(budget_stage)
        messages = await self._attach_user_image(
            request, provider, messages, first_call=budget_stage == "route_request"
        )
        metadata: dict[str, Any] = {
            "supports_tools": True,
            REQUEST_DEADLINE_METADATA_KEY: request.budget.deadline_monotonic,
        }
        if messages_contain_image(messages):
            # Fail closed at the provider boundary if a non-vision model is
            # ever handed image content.
            metadata["requires_vision"] = True
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
        # The user's global cap applies to every model; providers still clamp
        # it to the model's published ``maximum_output_tokens``.
        metadata["max_tokens"] = request.max_output_tokens
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
        # Which loop phase spends the tokens: the route call, tool-loop
        # decisions, or the tools-disabled answer synthesis.
        call_phase = (
            "routing" if budget_stage == "route_request"
            else "finalization" if terminal
            else "execution"
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
            request.budget.record_model_call(terminal=terminal)
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
                    call_phase,
                )
                return result
            except asyncio.TimeoutError as exc:
                usage = self._context_usage_for_request(llm_request)
                self._record_context_usage(request, usage, attempts, call_phase)
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
                    call_phase,
                )
                self._record_provider_failure(
                    request,
                    exc,
                    attempts=attempts,
                    protocol=protocol,
                    endpoint_host=endpoint_host,
                )
                if not exc.retryable or attempts >= self._model_attempt_limit(exc):
                    raise
                delay = self._model_retry_delay(request, attempts, exc)
                if delay is None:
                    raise
                request.budget.record_retry()
                request.budget.ensure_available("model_retry")
                await asyncio.sleep(delay)
                self._ensure_run_control(request)
                request.budget.ensure_available("model_retry")
            except (AgentRunControlSignal, LLMStructuredOutputError):
                raise
            except Exception as exc:
                # Raw exceptions here are adapter or transport faults that the
                # normalized provider error would otherwise hide.
                log_unexpected_failure(
                    LOGGER, exc, stage="model_call", level=logging.WARNING,
                    run_id=request.state.run_id or request.state.request_id,
                    provider=request.provider, model=request.model, attempt=attempts,
                )
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
                if not normalized.retryable or attempts >= self._model_attempt_limit(normalized):
                    raise normalized from exc
                delay = self._model_retry_delay(request, attempts, normalized)
                if delay is None:
                    raise normalized from exc
                request.budget.record_retry()
                request.budget.ensure_available("model_retry")
                await asyncio.sleep(delay)
                self._ensure_run_control(request)
                request.budget.ensure_available("model_retry")

    # -------------------------------------------------------------------------
    def _model_attempt_limit(self, error: LLMProviderRequestError) -> int:
        return self.transport_policy.attempts_for(
            rate_limited=error.code == "provider_rate_limited"
        )

    # -------------------------------------------------------------------------
    def _model_retry_delay(
        self,
        request: AgentLoopRequest,
        attempts: int,
        error: LLMProviderRequestError,
    ) -> float | None:
        """Return the pre-retry wait, or None when a provider-mandated wait exceeds the run budget."""

        delay = self.transport_policy.retry_delay(
            attempts,
            error.retry_after_seconds,
            rate_limited=error.code == "provider_rate_limited",
        )
        remaining = request.budget.remaining_seconds()
        if error.retry_after_seconds is None:
            return min(delay, remaining)
        return delay if delay <= remaining else None

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
        return {
            **merge_provider_context_usage(base_usage, provider_usage).to_dict(),
            "input_sections": estimate_input_sections(
                llm_request.messages, working_state_prefix=NATIVE_CONTEXT_PREFIX
            ),
        }

    # -------------------------------------------------------------------------
    @staticmethod
    def _record_context_usage(
        request: AgentLoopRequest,
        usage: dict[str, Any] | None,
        attempt: int,
        call_phase: str,
    ) -> None:
        if not isinstance(usage, dict):
            return
        usage = {**usage, "call_phase": call_phase}
        trace_usage = {
            "phase": "native_loop",
            "model": request.model,
            "attempt": attempt,
            "model_call": request.state.model_calls,
            **usage,
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
        for skipped in calls[len(bounded_calls):]:
            if len(state.tool_trace) < 128:
                state.tool_trace.append(
                    {
                        "call_id": skipped.id or "skipped-call",
                        "tool": skipped.name,
                        "status": "failed",
                        "error_code": "tool_call_not_executed",
                        "boundary": "loop_batch_limit",
                    }
                )
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
            if cached is not None and self._result_cacheable(call.name):
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
                    update={
                        "call_id": call.id or cached.call_id,
                        "summary": (
                            f"Already returned; take a different action. {cached.summary}"
                        ),
                    },
                    deep=True,
                )
            failed_count = state.failed_fingerprints.get(fingerprint, 0)
            if (
                call.name == "apply_map_plan"
                # A failed browser render is already proof that this exact
                # semantic map action made no progress, so its repeat is
                # rejected.  A watchdog timeout is the exception: the browser
                # did not answer in time, which says nothing about the plan,
                # so one identical retry is allowed.
                and self._render_retry_blocked(state, fingerprint)
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
                    f"The identical failing call to '{call.name}' was repeated "
                    f"{failed_count} times and was not executed again.",
                    recovery="replan",
                    data=build_rejection_feedback(
                        "repeated_failed_fingerprint",
                        call.name,
                        state,
                        exposed_tool_names,
                        repeated=True,
                    ),
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
            tasks = [asyncio.create_task(execute(call)) for call in bounded_calls]
            try:
                results = list(await asyncio.gather(*tasks))
            except BaseException:
                # A terminal signal (cancel, supersession, budget) in one call
                # must not leave sibling handlers writing after the run ends.
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                raise
        self._transition(state, AgentPhase.NORMALIZE_RESULT, request.budget)
        # A batch is one model decision: several calls sharing a mistake
        # receive one correction before the model has seen any feedback.
        batch_needs_correction = False
        failures_before_batch = state.consecutive_tool_failures
        for call, result in zip(bounded_calls, results, strict=False):
            self._ensure_run_control(request)
            fingerprint = self._fingerprint(call)
            if result.status != "failed":
                # Progress resets the guard: it bounds consecutive invalid
                # calls, not unrelated corrections spread across a long run.
                state.validation_corrections = 0
            if result.status == "failed":
                state.failed_fingerprints[fingerprint] = (
                    state.failed_fingerprints.get(fingerprint, 0) + 1
                )
                if result.error and (
                    result.error.error_type
                    in {
                        "malformed_call",
                        "tool_not_exposed",
                        "schema_validation",
                        "semantic_validation",
                        "policy_rejection",
                    }
                    or result.error.code == "repeated_failed_fingerprint"
                ):
                    batch_needs_correction = True
                if result.error and result.error.error_type in _CORRECTABLE_ERRORS:
                    self._grant_recovery_budget(request)
            elif result.tool_name != "apply_map_plan":
                # Only idempotent observations are replayable; live or
                # state-dependent tools must be re-executed for fresh results.
                if self._result_cacheable(result.tool_name):
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
            self._apply_result(
                state,
                result,
                target=normalize_target_key(str((call.arguments or {}).get("location_ref") or "")),
            )
        if batch_needs_correction and all(result.status == "failed" for result in results):
            state.validation_corrections += 1
        if results and all(result.status == "failed" for result in results):
            # One decision failed, however many parallel calls it contained.
            state.consecutive_tool_failures = failures_before_batch + 1
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
            or route.location_mode == "none"
            or (
                route.primary_domain
                in {CapabilityDomain.MAP_RENDERING, CapabilityDomain.MAP_STATE}
                and not route.secondary_domains
            )
            # A route that can neither execute a capability nor owes a
            # discovery has no use for a shortlist; searching with its
            # operation only reports a catalog miss the request never had.
            or not (
                route_allows_capability_execution(route)
                or "capabilities_discovered" in state.completion_requirements
            )
            or state.capability_ids
            or not (
                (route.location_mode == "search_area" and route_target_location_available(state))
                or any(result.tool_name == "resolve_geospatial_location" and result.status == "success" for result in results)
            )
        ):
            return None
        registered = self.tool_registry.get("discover_geospatial_capabilities")
        if registered is None:
            return None
        tool_limit = request.budget.max_tool_calls or request.max_tool_calls
        if state.tool_calls >= tool_limit:
            return None
        refresh_key = json.dumps(
            [sorted(state.location_refs), sorted(state.excluded_capability_ids)],
            separators=(",", ":"),
        )
        if refresh_key in state.discovery_refresh_keys:
            # The same places and exclusions yield the same shortlist.
            return None
        state.discovery_refresh_keys = [*state.discovery_refresh_keys, refresh_key][-16:]
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
            iteration=max(1, state.current_iteration),
            task_id=self._active_task_id(state),
            exposed_tool_names={"discover_geospatial_capabilities"},
        )
        self._ensure_run_control(request)
        self._transition(state, AgentPhase.NORMALIZE_RESULT, request.budget)
        self._apply_result(state, result)
        return result

    # -------------------------------------------------------------------------
    @staticmethod
    def _apply_result(state: AgentRunState, result: ToolResult, target: str = "") -> None:
        if not any(item.call_id == result.call_id for item in state.tool_results):
            state.tool_results.append(result)
        if result.status == "failed":
            state.consecutive_tool_failures += 1
            transient_exhausted = False
            if (
                result.error is not None
                and result.error.error_type in _TRANSIENT_FAILURE_TYPES
                and result.tool_name == "execute_geospatial_capability"
                and result.metadata.capability_id
            ):
                # A rate limit or timeout is retried once for the same source
                # and target; a repeat fails that target's data for good.
                key = f"{result.metadata.capability_id}|{target}"
                state.transient_failures[key] = state.transient_failures.get(key, 0) + 1
                if state.transient_failures[key] <= 1:
                    return
                transient_exhausted = True
                if target:
                    state.failed_data_targets[target] = result.metadata.capability_id
            if result.tool_name == "execute_geospatial_capability" and (
                transient_exhausted
                or (
                    result.error is not None
                    and result.error.recovery in {"choose_alternate_tool", "replan"}
                )
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
    def _result_cacheable(self, tool_name: str) -> bool:
        registered = self.tool_registry.get(tool_name)
        return registered is not None and registered.idempotent

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
    def _render_retry_blocked(state: AgentRunState, fingerprint: str) -> bool:
        failures = [
            observation
            for observation in state.render_observations
            if observation.status == "failed"
            and observation.action_fingerprint == fingerprint
        ]
        recorded = state.failed_render_fingerprints.get(fingerprint, 0)
        timeouts = sum(1 for item in failures if item.failure_code == "render_timeout")
        if failures and timeouts == len(failures):
            return timeouts >= 2
        return bool(failures) or recorded >= 1

    # -------------------------------------------------------------------------
    @staticmethod
    def _no_progress_correction(
        state: AgentRunState, tool_names: list[str]
    ) -> dict[str, Any]:
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
                    "The map was prepared, but the retrieved data does not satisfy "
                    "the request, so rendering again cannot fix it. Do not swap in "
                    "a different dataset for the one requested; tell the user what "
                    "is missing and any latest-available date the tool reported."
                    if render_failure.failure_stage == "backend_validation"
                    else "The browser did not confirm the previous map in time. Re-issue "
                    "the same map plan once, keeping every requested layer; if it "
                    "times out again, simplify the plan."
                    if render_failure.failure_code == "render_timeout"
                    and not AgentLoop._render_retry_blocked(
                        state, str(render_failure.action_fingerprint or "")
                    )
                    else "The previous map action failed browser rendering. Do not "
                    "repeat its action fingerprint; issue a materially revised "
                    "map plan or choose a supported renderable source."
                ),
            }
        correction: dict[str, Any] = {
            "observation_type": "pending_requirements",
            "status": "action_required",
            "pending_requirements": pending,
            "message": (
                "The response did not complete the deterministic completion "
                "contract. Select and execute the next required tool action."
            ),
        }
        closing = AgentLoop._tools_closing_requirements(pending, tool_names)
        if closing:
            correction["tools_that_close_pending"] = closing
        if state.evidence_refs:
            correction["evidence_refs"] = list(state.evidence_refs[-4:])
        return correction

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
        # Each invalid call returns a correction; stop only once the model has
        # used every allowed correction and is still calling tools invalidly.
        if state.validation_corrections > max_validation_corrections:
            return AgentLoop._invalid_call_stop(state)
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
        # A coverage rejection asks the user only when nothing else in the
        # batch succeeded; otherwise an in-coverage alternative is in hand.
        alternative_succeeded = any(result.status != "failed" for result in results)
        asking = next(
            (
                result
                for result in results
                if result.error is not None
                and result.error.recovery == "request_user_input"
                and not (
                    result.error.code == "policy_rejection" and alternative_succeeded
                )
            ),
            None,
        )
        if asking is not None and asking.error is not None:
            options = asking.data.get("options") if isinstance(asking.data, dict) else None
            state.clarification_options = normalize_clarification_options(
                options if isinstance(options, list) else None
            )
            return "clarification_required", asking.error.message
        if AgentLoop._render_recovery_requires_map_action(state, results):
            return (
                "no_progress",
                "Render recovery requires a materially different map action.",
            )
        uncovered_date = next(
            (
                result
                for result in results
                if result.tool_name == "execute_geospatial_capability"
                and result.status == "valid_empty"
                and result.metadata.coverage is not None
                and result.metadata.coverage.get("temporal_scope_satisfied") is False
                and result.metadata.coverage.get("latest_available_date")
            ),
            None,
        )
        if uncovered_date is not None:
            # The layer publishes no imagery for the requested day; no other
            # call can satisfy that day, so the provider's disclosure is final.
            return (
                "insufficient_evidence",
                "The requested date has no imagery." + AgentLoop._empty_result_note(state),
            )
        raster_only = next(
            (
                result.error.message
                for result in results
                if result.error is not None
                and result.error.code == RASTER_ONLY_CODE
                and result.error.recovery == "terminal"
            ),
            None,
        )
        if raster_only is not None:
            # No capability can supply records the request needs: answer now.
            return "insufficient_evidence", raster_only
        if any(result.status != "failed" for result in results):
            if (
                all(result.status == "valid_empty" for result in results)
                and not state.capability_ids
                and state.discovery_attempts >= max_discovery_attempts
                and not (
                    state.goal is not None
                    and state.goal.operation == "discover_available_map_data"
                )
            ):
                failure = AgentLoop._last_provider_failure(state)
                if failure is not None and failure.error is not None:
                    return (
                        "insufficient_evidence",
                        f"The {failure.metadata.provider_id} provider "
                        f"{AgentLoop._provider_failure_clause(failure.error.message)}, "
                        "and no alternative capability matched the request after discovery.",
                    )
                explanation = next(
                    (
                        str(result.summary)
                        for result in reversed(state.tool_results)
                        if result.tool_name == "discover_geospatial_capabilities"
                        and isinstance(result.data, dict)
                        and result.data.get("diagnostics")
                    ),
                    None,
                )
                return (
                    "insufficient_evidence",
                    "No supported capability matched the request after discovery."
                    + (f" {explanation}" if explanation else ""),
                )
            return None
        if results and all(result.status == "failed" for result in results):
            if state.consecutive_tool_failures >= max_consecutive_tool_failures:
                return "failed", AgentLoop._limitation_disclosure(
                    state,
                    "The agent stopped after repeated tool failures."
                    + AgentLoop._empty_result_note(state),
                )
            if actionable_recovery:
                return None
            return "failed", "The requested tool could not complete successfully."
        return None

    # -------------------------------------------------------------------------
    @staticmethod
    def _invalid_call_stop(state: AgentRunState) -> tuple[str, str]:
        """Classify a stop on repeated invalid calls and say so honestly.

        Values outside a declared range cannot be corrected into a valid call,
        so the request is unsupported.  Any other repeated invalid call means
        valid tools and arguments existed and the model did not produce them.
        """

        impossible: list[str] = []
        for result in reversed(state.tool_results):
            if result.status != "failed":
                break
            issues = result.data.get("issues") if is_json_object(result.data) else None
            for issue in issues if is_json_array(issues) else []:
                if is_json_object(issue) and issue.get("code") in UNSUPPORTED_CODES:
                    message = str(issue.get("message") or "")
                    if message and message not in impossible:
                        impossible.append(message)
        if impossible:
            text = (
                "That request cannot be satisfied as stated: "
                + " ".join(impossible[:3])
                + " Ask again with a value inside the valid range."
            )
            return "unsupported_request", AgentLoop._limitation_disclosure(state, text)
        last = state.tool_results[-1] if state.tool_results else None
        if last is not None and last.error is not None and last.error.code == "targets_not_in_view":
            return "model_incapable", AgentLoop._limitation_disclosure(
                state,
                "The map could not be fitted to show every requested place, "
                "so the request was not completed.",
            )
        text = (
            "The model repeatedly issued invalid tool calls even though valid "
            "tools and arguments were available, so the request was not completed."
        )
        return "model_incapable", AgentLoop._limitation_disclosure(state, text)

    # -------------------------------------------------------------------------
    @staticmethod
    def _empty_result_note(state: AgentRunState) -> str:
        """Carry a provider's own explanation of an empty result into the stop text."""

        warnings = next(
            (
                result.metadata.warnings
                for result in reversed(state.tool_results)
                if result.status == "valid_empty" and result.metadata.warnings
            ),
            list[str](),
        )
        return f" The provider reported: {' '.join(warnings)}" if warnings else ""

    # -------------------------------------------------------------------------
    @staticmethod
    def _last_provider_failure(state: AgentRunState) -> ToolResult | None:
        return next(
            (
                result
                for result in reversed(state.tool_results)
                if result.status == "failed"
                and result.error is not None
                and result.error.error_type in _PROVIDER_FAILURE_TYPES
                and result.metadata.provider_id
            ),
            None,
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def _provider_failure_clause(message: str) -> str:
        # "The provider did not respond ..." -> "did not respond ..."
        clause = message.strip().rstrip(".")
        prefix = "The provider "
        if clause.startswith(prefix):
            return clause[len(prefix) :]
        return f"failed ({clause})"

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
            state.clarification_options = list(route.clarification_options)
            return "clarification_required", text
        if state.prepared_map_session is not None:
            return "awaiting_render", text
        if text:
            tools = list(available_tools or [])
            pending = AgentLoop._pending_native_requirements(state)
            if "location_resolved" in pending and not state.location_refs and "?" in text:
                # No place was given (for example "Show it" in a new chat): asking
                # which place or data to show is a clarification, not a stall.
                return "clarification_required", text
            if pending:
                # A correction only helps when an exposed tool can close the
                # gap; otherwise the answer is the truthful partial outcome.
                return (
                    "no_progress"
                    if AgentLoop._tools_closing_requirements(pending, tools)
                    else "insufficient_evidence",
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
        mark_refs = self._mark_recovery_refs(state, route)
        location_ref = (
            None if mark_refs else self._location_only_map_recovery_ref(state, route)
        )
        if not mark_refs and location_ref is None:
            return []
        expected_revision = (
            state.active_map_session.overlay_collection.revision
            if state.active_map_session is not None
            else 0
        )
        actions: list[dict[str, Any]] = (
            [{"action": "mark_locations", "location_refs": mark_refs}]
            if mark_refs
            else [
                {
                    "action": "set_viewport",
                    "strategy": "fit_location",
                    "location_ref": str(location_ref),
                    **({"target_area_km2": route.target_area_km2} if route.target_area_km2 else {}),
                }
            ]
        )
        recovery_call = LLMToolCall(
            id=f"server-location-map-recovery-{state.request_id}",
            name="apply_map_plan",
            arguments={
                "expected_collection_revision": expected_revision,
                "actions": actions,
            },
        )

        return await self._execute_calls(
            request,
            [recovery_call],
            state,
            exposed_tool_names={"apply_map_plan"},
        )

    # -------------------------------------------------------------------------
    async def _recover_route_target(
        self,
        request: AgentLoopRequest,
        state: AgentRunState,
        tools: list[LLMToolDefinition],
    ) -> list[ToolResult]:
        """Resolve a map route's one named place when text survived a correction.

        The lookup and its argument are already fixed by the validated route.
        It runs at most once, through the normal typed tool boundary.
        """

        name = "resolve_geospatial_location"
        unresolved = unresolved_route_targets(state)
        if (
            not state.no_progress_corrections
            or state.route is None
            or state.route.presentation == "text"
            or len(unresolved) != 1
            or name not in {tool.name for tool in tools}
            or any(result.tool_name == name for result in state.tool_results)
        ):
            return []
        return await self._execute_calls(
            request,
            [
                LLMToolCall(
                    id=f"server-target-resolution-{state.request_id}",
                    name=name,
                    arguments={"query": unresolved[0]},
                )
            ],
            state,
            exposed_tool_names={name},
        )

    # -------------------------------------------------------------------------
    async def _recover_evidence_map(
        self,
        request: AgentLoopRequest,
        route: CapabilityRoute,
        state: AgentRunState,
    ) -> list[ToolResult]:
        """Map retrieved evidence when the model stalls with only the map left.

        Weaker models re-call a finished retrieval or run out of calls after
        the data is complete.  The next action is then unambiguous: show the
        run's evidence.  It runs once per run through the normal typed map
        boundary, so every map-plan validation still applies.
        """

        if (
            state.evidence_map_recovered
            or route.task_mode != "execute"
            or route.presentation not in {"map", "both"}
            or state.prepared_map_session is not None
            or self.tool_registry.get("apply_map_plan") is None
        ):
            return []
        pending = set(self._pending_native_requirements(state))
        if not pending or not pending <= {"map_candidate_prepared", "render_verified"}:
            return []
        layers = self._recoverable_evidence_layers(state, route)
        if not layers:
            return []
        state.evidence_map_recovered = True
        expected_revision = (
            state.active_map_session.overlay_collection.revision
            if state.active_map_session is not None
            else 0
        )
        recovery_call = LLMToolCall(
            id=f"server-evidence-map-recovery-{state.request_id}",
            name="apply_map_plan",
            arguments={
                "expected_collection_revision": expected_revision,
                "actions": [
                    *(
                        {
                            "action": "add_evidence_layer",
                            "evidence_ref": evidence_ref,
                            "capability_id": capability_id,
                        }
                        for evidence_ref, capability_id in layers
                    ),
                    {
                        "action": "set_viewport",
                        "strategy": "fit_evidence",
                        "evidence_refs": [evidence_ref for evidence_ref, _ in layers],
                    },
                ],
            },
        )
        return await self._execute_calls(
            request, [recovery_call], state, exposed_tool_names={"apply_map_plan"}
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def _recoverable_evidence_layers(
        state: AgentRunState, route: CapabilityRoute
    ) -> list[tuple[str, str]]:
        """Evidence the run itself produced that a map should show."""

        if route.analysis is not None:
            # A ranking is shown through its derived, located result set.
            derived = next(
                (
                    result
                    for result in reversed(state.tool_results)
                    if result.tool_name == "transform_evidence"
                    and result.status == "success"
                    and result.metadata.capability_id
                    and result.evidence_refs
                    and int(json_object(result.data).get("located_record_count") or 0) > 0
                ),
                None,
            )
            return (
                [(derived.evidence_refs[0], str(derived.metadata.capability_id))]
                if derived is not None
                else []
            )
        layers: list[tuple[str, str]] = []
        for result in state.tool_results:
            if (
                result.tool_name == "execute_geospatial_capability"
                and result.status in {"success", "partial"}
                and result.metadata.capability_id
                and result.metadata.result_type in {"features", "raster"}
            ):
                layers.extend(
                    (evidence_ref, str(result.metadata.capability_id))
                    for evidence_ref in result.evidence_refs
                )
        return list(dict.fromkeys(layers))[:8]

    # -------------------------------------------------------------------------
    @staticmethod
    def _location_only_map_recovery_ref(
        state: AgentRunState,
        route: CapabilityRoute | None = None,
    ) -> str | None:
        attempts = [
            result
            for result in state.tool_results
            if result.tool_name == "resolve_geospatial_location"
        ]
        location_results = [result for result in attempts if result.status == "success"]
        if len(location_results) < len(attempts) or (
            state.route is not None and unresolved_route_targets(state)
        ):
            # A lookup this turn failed or was ambiguous, or a requested place
            # is still unresolved: a location hydrated from an earlier turn
            # (a parent such as "Berlin") must not stand in for it.
            return None
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
        if route is not None and len(route.target_refs) > 1:
            # One viewport fit cannot present several named targets; leave
            # the obligation to the model instead of claiming them covered.
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
    def _mark_recovery_refs(
        state: AgentRunState,
        route: CapabilityRoute,
    ) -> list[str]:
        """Location refs of every place a marking route names, once all resolved."""

        if not is_mark_locations_operation(route.operation) or unresolved_route_targets(state):
            return []
        refs: list[str] = []
        for target in route.target_refs:
            # The target's own lookup first: another lookup can return a
            # building whose label also names this place.
            ref = next(
                (
                    key
                    for key in state.location_refs
                    if location_ref_matches(str(target), str(key), None)
                ),
                None,
            ) or next(
                (
                    key
                    for key, location in state.location_refs.items()
                    if location_ref_matches(str(target), str(key), location.label)
                ),
                None,
            )
            if ref is None:
                return []
            refs.append(ref)
        return list(dict.fromkeys(refs))

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
        if is_mark_locations_operation(route.operation):
            return bool(AgentLoop._mark_recovery_refs(state, route))
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
    def _bind_search_area(state: AgentRunState, route: CapabilityRoute) -> None:
        from server.services.agent.location_resolver import find_macro_region

        if route.location_mode != "search_area":
            return
        for ref in route.target_refs:
            location = find_macro_region(ref)
            if location is not None:
                state.location_refs[ref] = location

    # -------------------------------------------------------------------------
    @staticmethod
    def _grant_recovery_budget(request: AgentLoopRequest) -> None:
        """Give a simple run the complex budget once it must correct a tool call.

        The simple caps fit a clean trajectory; one invalid call would
        otherwise exhaust them before the model can apply the correction.
        """

        budget = request.budget
        if budget.run_profile != "simple":
            return
        budget.promote("complex")
        budget.configure_limits(
            max_model_calls=request.max_model_calls,
            max_tool_calls=request.max_tool_calls,
            max_state_transitions=request.max_state_transitions,
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def _budget_profile(route: CapabilityRoute) -> str:
        if (
            route.analysis is not None
            or route.presentation in {"map", "both"}
            or route.secondary_domains
            or len(route.capability_queries) > 1
            or len(route.target_refs) > 1
            or route.primary_domain is CapabilityDomain.SPATIAL_ANALYSIS
        ):
            return "complex"
        return "simple"

    # -------------------------------------------------------------------------
    @staticmethod
    def _compile_native_goal(
        state: AgentRunState,
        route: CapabilityRoute,
        *,
        requests_entities: bool = False,
        servable_queries: Callable[[Sequence[str]], list[str]] | None = None,
    ) -> None:
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
        target_requirements = [
            requirement.model_copy(
                update={
                    "temporal_scope": (
                        requirement.temporal_scope
                        if requirement.temporal_scope is not None
                        and requirement.temporal_scope != AgentTemporalScope()
                        else route.temporal_scope
                        if route_has_temporal_scope
                        else None
                    ),
                    "spatial_scope": requirement.spatial_scope or route.spatial_scope,
                }
            )
            for requirement in route.target_requirements
        ]
        per_target_temporal = any(
            requirement.temporal_scope is not None
            and requirement.temporal_scope != AgentTemporalScope()
            for requirement in target_requirements
        )
        spatial_scope = (
            [route.spatial_scope.model_dump(mode="json")]
            if route.spatial_scope is not None
            else []
        )
        filters = dict(route.filters)
        requirements: list[str] = []
        if route.location_mode != "none":
            requirements.append("search_area_bound" if route.location_mode == "search_area" else "location_resolved")
        if route.analysis is not None:
            requirements.append("result_locations_derived")
        route_domains = {route.primary_domain, *route.secondary_domains}
        text_location_resolution_only = is_text_location_lookup(route)
        text_evidence_inspection_only = (
            route.task_mode == "execute"
            and route.presentation == "text"
            and operation == "inspect_evidence"
        )
        # Provider data is only an obligation where the route may execute
        # capabilities; otherwise the contract could never be satisfied.
        data_route = route_allows_capability_execution(route)
        capability_discovery_only = operation == "discover_available_map_data"
        # Distance, bearing, extent or country-of questions about places are
        # answered by deterministic measurement, never by a model estimate.
        measurement_route = (
            route.task_mode == "execute"
            and route.analysis is None
            and route.location_mode != "none"
            and route.primary_domain
            in {CapabilityDomain.SPATIAL_ANALYSIS, CapabilityDomain.ROUTING}
            and CapabilityDomain.DATA_RETRIEVAL not in route_domains
        )
        requires_provider_data = (
            route.task_mode == "execute"
            and data_route
            and not measurement_route
            and not text_location_resolution_only
            and not text_evidence_inspection_only
            and not capability_discovery_only
            and not is_location_only_map_request(
                state.user_message, route, requests_entities=requests_entities
            )
        )
        if measurement_route:
            requirements.append("measurement_computed")
        if requires_provider_data:
            requirements.append("required_data_retrieved")
        elif route.task_mode == "execute" and capability_discovery_only:
            requirements.append("capabilities_discovered")
        elif text_evidence_inspection_only:
            requirements.append("evidence_inspected")
        temporal_scope_needed = per_target_temporal or bool(
            route_has_temporal_scope
            and temporal_scope
            and (
                temporal_scope.get("mode") != "none"
                or temporal_scope.get("start_time_iso") is not None
                or temporal_scope.get("end_time_iso") is not None
                or temporal_scope.get("reference_time_iso") is not None
            )
        )
        if route.task_mode == "execute" and temporal_scope_needed:
            requirements.append("temporal_scope_applied")
        if (
            route.task_mode == "execute"
            and route.spatial_scope is not None
            and not capability_discovery_only
        ):
            requirements.append("spatial_scope_applied")
        if route.presentation in {"map", "both"}:
            requirements.append("map_candidate_prepared")
            if is_mark_locations_operation(route.operation):
                requirements.append("locations_marked")
        state.completion_requirements = list(dict.fromkeys(requirements))
        data_obligations = (
            (servable_queries or list)(list(dict.fromkeys(route.capability_queries))[:4])
            if requires_provider_data and len(route.capability_queries) > 1
            else []
        )
        state.goal = AgentGoal(
            goal=state.user_message,
            task_mode=route.task_mode,
            presentation=route.presentation,
            operation=operation,
            location_mode=route.location_mode,
            analysis=route.analysis,
            target_ids=target_ids,
            temporal_scope=temporal_scope,
            spatial_scope=spatial_scope,
            target_requirements=target_requirements,
            filters=filters,
            obligations=derive_request_obligations(
                route,
                target_ids=target_ids,
                target_requirements=target_requirements,
                requirements=state.completion_requirements,
                data_variables=data_obligations,
            ),
        )
        state.completion_contract = CompletionContract(
            operation=operation,
            data_requirement=("provider_data" if requires_provider_data else "none"),
            requirements=list(state.completion_requirements),
            location_required=route.location_mode != "none",
            evidence_required="required_data_retrieved" in state.completion_requirements,
            data_obligations=data_obligations,
            map_preparation_required="map_candidate_prepared"
            in state.completion_requirements,
            temporal_scope_required=temporal_scope_needed,
            spatial_scope_required=bool(spatial_scope) and not capability_discovery_only,
            render_verification_required=route.presentation in {"map", "both"},
            render_verified=state.render_verified,
        )
        AgentLoop._initialize_task_state_for_route(state, route)

    # -------------------------------------------------------------------------
    @staticmethod
    def _tools_closing_requirements(
        pending: list[str], tool_names: list[str]
    ) -> list[str]:
        """Exposed tools whose results can move a pending requirement.

        A requirement outside the table is treated as closable by any tool,
        so an unknown obligation never ends a run early.
        """

        closing: set[str] = set()
        for requirement in pending:
            tools = _REQUIREMENT_TOOLS.get(requirement)
            if tools is None:
                return list(tool_names)
            closing |= tools
        return [name for name in tool_names if name in closing]

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
        if requested_transform_unmet(state):
            required_names.append("requested_transform_applied")
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
        # A hydrated run already carries tool and render observations in the
        # canonical context; repeating them here only spends input tokens.
        observed = not state.context_hydrated
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
        ] if observed else []
        payload: dict[str, Any] = {
            "phase": state.phase.value,
            # The task ledger in the canonical context already lists every
            # obligation, and the declared route copy only repeats them.
            "goal": (
                state.goal.model_dump(mode="json", exclude={"obligations"})
                if state.goal is not None
                else None
            ),
            "completion_contract": (
                state.completion_contract.model_dump(mode="json")
                if state.completion_contract is not None
                else None
            ),
            "route": (
                state.route.model_dump(mode="json", exclude={"obligations"})
                if state.route
                else None
            ),
            "capability_ids": list(state.capability_ids),
            "excluded_capability_ids": list(state.excluded_capability_ids),
            "location_refs": sorted(state.location_refs),
            "evidence_refs": list(state.evidence_refs),
            "prepared_map": bool(state.prepared_map_session),
            "render_verified": state.render_verified,
            "render_attempts": state.render_attempts,
            "active_map_collection_revision": (
                state.active_map_session.overlay_collection.revision
                if state.active_map_session is not None
                else 0
            ),
        }
        # Evidence of earlier turns compatible with this goal: an identical
        # execute call is answered from it without a provider request.
        reusable = {
            item.task_id: item.evidence_refs for item in state.prior_tasks if item.kind == "data"
        }
        if reusable:
            payload["reusable_evidence"] = reusable
        if observed:
            payload["render_observations"] = [
                item.model_dump(mode="json") for item in state.render_observations[-4:]
            ]
            payload["tool_results"] = tool_result_summaries
        serialized = json.dumps(payload, separators=(",", ":"), default=str)
        if len(serialized) <= max(256, limit):
            return serialized
        compact = dict(payload)
        if observed:
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
        minimal: dict[str, Any] = {
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
        }
        if observed:
            minimal["render_observations"] = [
                item.model_dump(mode="json") for item in state.render_observations[-2:]
            ]
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
            "location_mode": state.goal.location_mode,
            "analysis": state.goal.analysis.model_dump(mode="json") if state.goal.analysis else None,
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
            "location_mode": state.route.location_mode,
            "analysis": state.route.analysis.model_dump(mode="json") if state.route.analysis else None,
            "capability_queries": list(state.route.capability_queries[:4]),
            "explicit_capability_ids": list(state.route.explicit_capability_ids[:8]),
            "operation": state.route.operation,
        }

    # -------------------------------------------------------------------------
    @staticmethod
    def _assistant_and_tool_messages(result: LLMResult) -> list[dict[str, Any]]:
        if result.provider_continuation is not None:
            return [{
                "role": "assistant",
                "google_content": result.provider_continuation,
                "tool_calls": [
                    {"id": call.id, "name": call.name, "arguments": call.arguments or {}}
                    for call in result.tool_calls
                ],
            }]
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
        # Every model call needs exactly its own result.  Results may also
        # carry server-issued calls (discovery refresh, map recovery), and a
        # batch can be truncated by the per-step limit, so pair by call id.
        results_by_id = {result.call_id: result for result in results}
        messages: list[dict[str, Any]] = []
        for index, call in enumerate(calls):
            result = (
                results_by_id.get(call.id)
                if call.id
                else results[index] if index < len(results) else None
            )
            if result is None:
                result = AgentLoop._failure_result(
                    call,
                    "tool_call_not_executed",
                    "This tool call was not executed because the step exceeded "
                    "its tool-call limit. Issue it again only if still needed.",
                    recovery="replan",
                )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "name": call.name,
                    "content": ModelObservation.from_tool_result(
                        result, max_chars=max_chars
                    ).model_dump_json(exclude_none=True),
                }
            )
        return messages

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
        data: dict[str, Any] | None = None,
    ) -> ToolResult:
        return ToolResult(
            call_id=call.id or "repeated-call",
            tool_name=call.name,
            status="failed",
            summary=message,
            data=data,
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
        # Terminal causes map onto the existing public stop reasons and
        # failure categories; the cause itself stays in the trace.
        stopped_reason, failure_category = _TERMINAL_CAUSES.get(reason, (reason, None))
        if reason in _TERMINAL_CAUSES:
            state.termination_reason = reason
        reason = stopped_reason
        if reason != "clarification_required":
            state.clarification_options = []
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
            failure_category=failure_category,
            vision_capture_requested=(
                self._capture_requested_for_outcome(request)
                if reason == "awaiting_render"
                else False
            ),
        )

    # -------------------------------------------------------------------------
    def _capture_requested_for_outcome(
        self,
        request: AgentLoopRequest,
    ) -> bool:
        """Whether the render handshake should request a browser capture.

        Resolved only when the loop suspends for a render; the routing and
        iteration paths never trigger captures.
        """

        try:
            provider = self.provider_factory.get_provider(request.provider)
        except Exception:
            return False
        supports_vision = (
            provider.supports_vision(request.model)
            if hasattr(provider, "supports_vision")
            else None
        )
        engine = VisionPolicyEngine(
            policy=request.vision_policy,
            vision_supported=supports_vision,
            max_vision_calls=request.vision_max_calls,
        )
        return engine.should_capture(request.state)

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
    async def _exhausted_outcome(
        self,
        request: AgentLoopRequest,
        provider: AgentProvider,
        messages: list[dict[str, Any]],
        reason: str,
    ) -> AgentLoopOutcome:
        """Stop on an exhausted budget, summarizing any evidence gathered."""

        state = request.state
        text: str | None = None
        try:
            recovered = state.route is not None and bool(
                await self._recover_evidence_map(request, state.route, state)
            )
        except (ExecutionBudgetExceeded, TimeoutError):
            recovered = False
        if recovered and state.prepared_map_session is not None:
            # The data was complete and only the map was missing; the server
            # prepared it, and the render acknowledgement finalizes the run.
            await self._emit_completion_decision(
                request, reason="awaiting_render", status="terminal"
            )
            state.termination_reason = "awaiting_render"
            return self._outcome(
                state,
                "The map is being prepared from the evidence already retrieved.",
                "awaiting_render",
                request,
            )
        if state.route is not None and state.route.task_mode == "answer" and not state.tool_results:
            # Reasoning models can end a plain-answer turn with reasoning only
            # and no content; the reserved slot gives a conversation one more
            # chance, and a text answer is the whole goal of that route.
            text = await self._terminal_synthesis(
                request, provider, messages, reason="conversation_answer"
            )
            if text:
                await self._emit_completion_decision(
                    request, reason="goal_satisfied", status="terminal"
                )
                state.termination_reason = "goal_satisfied"
                return self._outcome(state, text, "goal_satisfied", request)
        if any(result.status != "failed" for result in state.tool_results):
            text = await self._finalize_iteration_exhaustion(
                request, provider, messages, stop_reason=reason
            )
        return self._budget_outcome(state, request, reason, final_text=text)

    # -------------------------------------------------------------------------
    def _budget_outcome(
        self,
        state: AgentRunState,
        request: AgentLoopRequest,
        reason: str,
        *,
        final_text: str | None = None,
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
            final_text or "The agent reached its configured execution limit.",
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
    @staticmethod
    def _limitation_disclosure(state: AgentRunState, text: str) -> str:
        pending = AgentLoop._pending_native_requirements(state)
        if not pending:
            return text
        unresolved = unresolved_route_targets(state)
        note = (
            f"Not completed: {describe_requirements(pending)}"
            + (f" ({', '.join(unresolved)})" if unresolved else "")
            + "."
        )
        gap = imagery_only_note(state)
        if gap:
            note = f"{note} {gap}"
        return f"{text.rstrip()}\n\n{note}" if note not in text else text

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
        marker = "The map was not updated"
        if marker in text:
            return text
        summary = (
            observation.failure_summary
            or "The renderer did not verify the prepared map."
        )
        failed_checks = "Required map completion checks failed: "
        if summary.startswith(failed_checks):
            # Backend validation names internal obligations; users need the
            # meaning, while the run trace keeps the exact codes.
            names = [item.strip() for item in summary[len(failed_checks):].split(",")]
            summary = describe_requirements([item for item in names if item]) + "."
            summary = summary[:1].upper() + summary[1:]
        suffix = f"{marker}: {summary} The previous map is still shown."
        return f"{text.rstrip()}\n\n{suffix}" if text.strip() else suffix


__all__ = [
    "AgentLoop",
    "AgentLoopOutcome",
    "AgentLoopRequest",
]
