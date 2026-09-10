"""Unified native-v2 state machine for bounded agent execution."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from server.domain.agent.capability_route import (
    AgentPhase,
    AgentState,
    CapabilityRoute,
)
from server.domain.agent.reliability import AgentExecutionBudget
from server.domain.agent.tool_result import (
    ToolExecutionError,
    ToolExecutionMetadata,
    ToolResult,
)
from server.domain.llm.types import LLMRequest, LLMResult, LLMToolCall, LLMToolDefinition
from server.prompts.capability_route import build_capability_route_prompt
from server.services.agent.capability_router import CapabilityRouter
from server.services.agent.completion import CompletionEvaluator
from server.services.agent.tool_executor import ToolExecutor
from server.services.agent.tool_registry import ToolRegistry
from server.services.llm.errors import LLMProviderRequestError, LLMStructuredOutputError


###############################################################################
class AgentProvider(Protocol):
    async def achat(
        self,
        request: LLMRequest,
        *,
        tools: Sequence[LLMToolDefinition] | None = None,
        tool_choice: str | None = "auto",
        response_json_schema: dict[str, Any] | None = None,
    ) -> LLMResult: ...


class AgentProviderFactory(Protocol):
    def get_provider(self, provider: str) -> AgentProvider: ...


###############################################################################
@dataclass(frozen=True)
class AgentLoopRequest:
    provider: str
    model: str
    state: AgentState
    budget: AgentExecutionBudget
    messages: list[dict[str, Any]] = field(default_factory=list)
    temperature: float = 0.2
    max_model_call_seconds: float = 60.0
    max_iterations: int = 12
    max_model_calls: int = 10
    max_tool_calls: int = 20
    max_state_transitions: int = 32
    max_parallel_tool_calls: int = 8
    max_consecutive_tool_failures: int = 3
    max_same_failed_fingerprint: int = 2
    max_route_corrections: int = 1
    max_validation_corrections: int = 2
    max_tool_result_chars: int = 4096


@dataclass(frozen=True)
class AgentLoopOutcome:
    final_text: str
    state: AgentState
    stopped_reason: Literal[
        "goal_satisfied",
        "awaiting_render",
        "clarification_required",
        "insufficient_evidence",
        "provider_error",
        "context_limit",
        "tool_budget_exhausted",
        "run_deadline_exhausted",
        "no_progress",
        "cancelled",
        "superseded",
        "failed",
    ]
    model_calls: int
    tool_results: list[ToolResult] = field(default_factory=list)
    failure_category: str | None = None
    failure_detail: str | None = None


@dataclass(frozen=True)
class AgentLoopPreview:
    """Route/exposure result for shadow mode; it never calls a provider."""

    state: AgentState
    route: CapabilityRoute | None
    exposed_tool_names: list[str] = field(default_factory=list)
    stopped_reason: str = "shadow_preview"
    failure_detail: str | None = None


###############################################################################
class AgentLoop:
    """Own routing, progressive tool exposure, execution, and stopping."""

    ROUTE_TOOL = LLMToolDefinition(
        name="route_request",
        description="Select one bounded high-level AEGIS capability route.",
        parameters_json_schema=CapabilityRoute.model_json_schema(),
    )

    def __init__(
        self,
        *,
        provider_factory: AgentProviderFactory,
        capability_router: CapabilityRouter,
        tool_registry: ToolRegistry,
        tool_executor: ToolExecutor,
    ) -> None:
        self.provider_factory = provider_factory
        self.capability_router = capability_router
        self.tool_registry = tool_registry
        self.tool_executor = tool_executor

    # -------------------------------------------------------------------------
    async def run(self, request: AgentLoopRequest) -> AgentLoopOutcome:
        state = request.state
        provider = self.provider_factory.get_provider(request.provider)
        messages = list(request.messages) or [
            {"role": "user", "content": state.user_message}
        ]
        final_text = ""
        try:
            self._transition(state, AgentPhase.ROUTE_REQUEST)
            route_result = await self._route(request, provider, messages)
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

            for iteration in range(max(1, request.max_iterations)):
                if state.model_calls >= request.max_model_calls:
                    return self._budget_outcome(state, request, "model_budget_exhausted")
                self._transition(state, AgentPhase.BUILD_TOOL_CONTEXT)
                tools = self.tool_registry.expose(state)
                if not tools and route.task_mode == "execute" and not state.tool_results:
                    return self._failed(
                        state,
                        request,
                        "No actionable tool is available for this route.",
                        category="model_capability",
                    )
                self._transition(state, AgentPhase.MODEL_STEP)
                result = await self._model_step(
                    request,
                    provider,
                    messages,
                    tools,
                )
                if result.tool_calls:
                    messages.extend(self._assistant_and_tool_messages(result))
                    tool_results = await self._execute_calls(
                        request,
                        result.tool_calls,
                        state,
                    )
                    messages.extend(
                        self._tool_result_messages(result.tool_calls, tool_results)
                    )
                    self._transition(state, AgentPhase.UPDATE_STATE)
                    self._transition(state, AgentPhase.EVALUATE_STOP)
                    stop = self._evaluate_stop(
                        state,
                        route,
                        tool_results,
                        max_consecutive_tool_failures=request.max_consecutive_tool_failures,
                        max_validation_corrections=request.max_validation_corrections,
                    )
                    if stop is not None:
                        state.termination_reason = stop[0]
                        return self._outcome(state, stop[1], stop[0], request)
                    continue

                final_text = result.content.strip()
                self._transition(state, AgentPhase.EVALUATE_STOP)
                stop = self._evaluate_text_stop(state, route, final_text)
                if stop is not None:
                    state.termination_reason = stop[0]
                    return self._outcome(state, final_text, stop[0], request)
                messages.append({"role": "assistant", "content": final_text})
                if iteration + 1 >= request.max_iterations:
                    return self._budget_outcome(state, request, "no_progress")
            return self._budget_outcome(state, request, "no_progress")
        except asyncio.CancelledError:
            state.termination_reason = "cancelled"
            return self._outcome(state, final_text, "cancelled", request)
        except TimeoutError:
            state.termination_reason = "run_deadline_exhausted"
            return self._outcome(state, final_text, "run_deadline_exhausted", request)
        except LLMStructuredOutputError as exc:
            return self._failed(state, request, "The selected model could not complete this request.", category=exc.category)
        except Exception:
            return self._failed(state, request, "The agent stopped after an unexpected execution failure.", category="provider_error")

    # -------------------------------------------------------------------------
    def preview(self, request: AgentLoopRequest) -> AgentLoopPreview:
        """Compute native exposure from an existing route without egress."""

        state = request.state
        route = state.route
        if route is None:
            state.termination_reason = "failed"
            self._transition(state, AgentPhase.FAILED)
            return AgentLoopPreview(
                state=state,
                route=None,
                stopped_reason="failed",
                failure_detail="Shadow exposure requires a validated route.",
            )
        self._transition(state, AgentPhase.BUILD_TOOL_CONTEXT)
        exposed = self.tool_registry.expose(state)
        state.termination_reason = "shadow_preview"
        self._transition(state, AgentPhase.FINALIZE)
        return AgentLoopPreview(
            state=state,
            route=route,
            exposed_tool_names=[item.name for item in exposed],
        )

    # -------------------------------------------------------------------------
    async def _route(
        self,
        request: AgentLoopRequest,
        provider: AgentProvider,
        messages: list[dict[str, Any]],
    ) -> tuple[str | None, str, CapabilityRoute | None]:
        correction_messages = [
            {"role": "system", "content": build_capability_route_prompt()},
            *messages,
        ]
        for attempt in range(request.max_route_corrections + 1):
            result = await self._model_call(
                request,
                provider,
                correction_messages,
                [self.ROUTE_TOOL],
                tool_choice="required",
            )
            call = result.tool_calls[0] if result.tool_calls else None
            if (
                call is not None
                and call.name == self.ROUTE_TOOL.name
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
                    if decision.status == "accepted":
                        request.state.capability_ids = list(decision.capability_ids)
                        return None, "", proposed
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
            request.state.route_corrections = attempt + 1
            correction_messages.append(
                {
                    "role": "user",
                    "content": "Return one valid route_request call matching the supplied schema.",
                }
            )
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
        model_messages = [*messages, {"role": "system", "content": working}]
        return await self._model_call(
            request,
            provider,
            model_messages,
            tools,
            tool_choice="auto" if tools else "none",
        )

    # -------------------------------------------------------------------------
    async def _model_call(
        self,
        request: AgentLoopRequest,
        provider: AgentProvider,
        messages: list[dict[str, Any]],
        tools: list[LLMToolDefinition],
        *,
        tool_choice: str,
    ) -> LLMResult:
        request.budget.ensure_available("model_step")
        remaining = request.budget.remaining_seconds()
        timeout = min(max(0.01, remaining), max(0.01, request.max_model_call_seconds))
        llm_request = LLMRequest(
            model=request.model,
            provider=request.provider,
            messages=messages,
            temperature=request.temperature,
            tools=tools or None,
            tool_choice=tool_choice,
            metadata={"supports_tools": True},
        )
        attempts = 0
        while True:
            attempts += 1
            request.state.model_calls += 1
            request.budget.record_model_call()
            try:
                return await asyncio.wait_for(
                    provider.achat(
                        llm_request,
                        tools=tools or None,
                        tool_choice=tool_choice,
                    ),
                    timeout=timeout,
                )
            except LLMProviderRequestError as exc:
                if not exc.retryable or attempts >= 2:
                    raise
                request.budget.record_retry()
                await asyncio.sleep(min(0.25, request.budget.remaining_seconds()))

    # -------------------------------------------------------------------------
    async def _execute_calls(
        self,
        request: AgentLoopRequest,
        calls: list[LLMToolCall],
        state: AgentState,
    ) -> list[ToolResult]:
        remaining_tool_calls = request.max_tool_calls - state.tool_calls
        if remaining_tool_calls <= 0:
            return [
                self._failure_result(
                    call,
                    "tool_budget_exhausted",
                    "The configured tool-call limit was reached.",
                    recovery="replan",
                )
                for call in calls
            ]
        bounded_calls = calls[: min(request.max_parallel_tool_calls, remaining_tool_calls)]
        semaphore = asyncio.Semaphore(max(1, request.max_parallel_tool_calls))

        async def execute(call: LLMToolCall) -> ToolResult:
            fingerprint = self._fingerprint(call)
            cached = state.successful_fingerprints.get(fingerprint)
            if cached is not None:
                return cached.model_copy(
                    update={"call_id": call.id or cached.call_id}, deep=True
                )
            failed_count = state.failed_fingerprints.get(fingerprint, 0)
            if failed_count >= request.max_same_failed_fingerprint:
                return self._failure_result(
                    call,
                    "repeated_failed_fingerprint",
                    "The same failing tool call was not repeated.",
                    recovery="replan",
                )
            async with semaphore:
                self._transition(state, AgentPhase.VALIDATE_ACTION)
                result = await self.tool_executor.execute_tool(
                    call,
                    state,
                    request.budget,
                )
                self._transition(state, AgentPhase.NORMALIZE_RESULT)
                return result

        if any(call.name == "apply_map_plan" for call in bounded_calls):
            results: list[ToolResult] = []
            for call in bounded_calls:
                results.append(await execute(call))
        else:
            results = await asyncio.gather(*(execute(call) for call in bounded_calls))
        for call, result in zip(bounded_calls, results, strict=False):
            fingerprint = self._fingerprint(call)
            if result.status == "failed":
                state.failed_fingerprints[fingerprint] = (
                    state.failed_fingerprints.get(fingerprint, 0) + 1
                )
                if result.error and result.error.error_type in {
                    "malformed_call",
                    "schema_validation",
                    "semantic_validation",
                    "policy_rejection",
                }:
                    state.validation_corrections += 1
            else:
                state.successful_fingerprints[fingerprint] = result
            self._apply_result(state, result)
        return results

    # -------------------------------------------------------------------------
    @staticmethod
    def _apply_result(state: AgentState, result: ToolResult) -> None:
        if not any(item.call_id == result.call_id for item in state.tool_results):
            state.tool_results.append(result)
        if result.status == "failed":
            state.consecutive_tool_failures += 1
            return
        state.consecutive_tool_failures = 0
        for evidence_ref in result.evidence_refs:
            if evidence_ref not in state.evidence_refs:
                state.evidence_refs.append(evidence_ref)

    # -------------------------------------------------------------------------
    @staticmethod
    def _fingerprint(call: LLMToolCall) -> str:
        payload = {
            "name": call.name,
            "arguments": call.arguments,
            "parse_error": call.parse_error,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    # -------------------------------------------------------------------------
    def _evaluate_stop(
        self,
        state: AgentState,
        route: CapabilityRoute,
        results: list[ToolResult],
        *,
        max_consecutive_tool_failures: int,
        max_validation_corrections: int,
    ) -> tuple[str, str] | None:
        if state.prepared_map_session is not None:
            return "awaiting_render", "The map candidate is awaiting render acknowledgment."
        if state.consecutive_tool_failures >= max_consecutive_tool_failures:
            return "failed", "The agent stopped after repeated tool failures."
        if state.validation_corrections >= max_validation_corrections:
            return "failed", "The agent stopped after repeated invalid tool calls."
        if any(result.status != "failed" for result in results):
            return None
        if results and all(result.status == "failed" for result in results):
            if any(result.error and result.error.retryable for result in results):
                return None
            return "failed", "The requested tool could not complete successfully."
        return None

    # -------------------------------------------------------------------------
    @staticmethod
    def _evaluate_text_stop(
        state: AgentState,
        route: CapabilityRoute,
        text: str,
    ) -> tuple[str, str] | None:
        if route.task_mode == "clarify":
            return "clarification_required", text
        if state.prepared_map_session is not None:
            return "awaiting_render", text
        if text:
            evaluation = CompletionEvaluator.evaluate_proposed_stop(
                canonical_request=state.canonical_request,
                presentation_required=route.presentation in {"map", "both"},
                map_prepared=False,
                evidence_refs=state.evidence_refs,
                available_tools=[],
                clarification_required=False,
                provider_error=False,
            )
            if not evaluation.satisfied:
                return evaluation.reason, text
            return "goal_satisfied", text
        return None

    # -------------------------------------------------------------------------
    @staticmethod
    def _transition(state: AgentState, phase: AgentPhase) -> None:
        previous = state.phase.value
        if state.phase is phase:
            return
        state.phase = phase
        state.transitions += 1
        state.transition_trace.append({"from": previous, "to": phase.value})

    # -------------------------------------------------------------------------
    @staticmethod
    def _working_state_message(state: AgentState, limit: int) -> str:
        payload = {
            "phase": state.phase.value,
            "route": state.route.model_dump(mode="json") if state.route else None,
            "capability_ids": list(state.capability_ids),
            "location_refs": sorted(state.location_refs),
            "evidence_refs": list(state.evidence_refs),
            "prepared_map": bool(state.prepared_map_session),
            "tool_results": [
                {
                    "call_id": item.call_id,
                    "tool_name": item.tool_name,
                    "status": item.status,
                    "summary": item.summary,
                    "evidence_refs": list(item.evidence_refs),
                    "error_code": item.error.code if item.error else None,
                }
                for item in state.tool_results[-8:]
            ],
        }
        serialized = json.dumps(payload, separators=(",", ":"), default=str)
        return serialized[: max(256, limit)]

    # -------------------------------------------------------------------------
    @staticmethod
    def _assistant_and_tool_messages(result: LLMResult) -> list[dict[str, Any]]:
        return [
            {
                "role": "assistant",
                "content": result.content or None,
                "tool_calls": [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": call.name,
                            "arguments": json.dumps(call.arguments or {}),
                        },
                    }
                    for call in result.tool_calls
                ],
            }
        ]

    # -------------------------------------------------------------------------
    @staticmethod
    def _tool_result_messages(
        calls: list[LLMToolCall], results: list[ToolResult]
    ) -> list[dict[str, Any]]:
        return [
            {
                "role": "tool",
                "tool_call_id": call.id,
                "name": call.name,
                "content": result.model_dump_json(exclude={"data"}),
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
        state: AgentState,
        final_text: str,
        reason: str,
        request: AgentLoopRequest,
    ) -> AgentLoopOutcome:
        target_phase = (
            AgentPhase.AWAIT_RENDER
            if reason == "awaiting_render"
            else AgentPhase.FAILED
            if reason in {"failed", "provider_error", "run_deadline_exhausted"}
            else AgentPhase.FINALIZE
        )
        self._transition(state, target_phase)
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
        state: AgentState,
        request: AgentLoopRequest,
        detail: str,
        *,
        category: str,
    ) -> AgentLoopOutcome:
        state.termination_reason = "failed"
        self._transition(state, AgentPhase.FAILED)
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
        state: AgentState,
        request: AgentLoopRequest,
        reason: str,
    ) -> AgentLoopOutcome:
        stable_reason = (
            "tool_budget_exhausted"
            if reason == "model_budget_exhausted"
            else reason
        )
        state.termination_reason = stable_reason
        self._transition(state, AgentPhase.FAILED)
        return AgentLoopOutcome(
            final_text="The agent reached its configured execution limit.",
            state=state,
            stopped_reason=stable_reason,  # type: ignore[arg-type]
            model_calls=state.model_calls,
            tool_results=list(state.tool_results),
            failure_category="context_limit" if reason == "no_progress" else None,
        )


__all__ = [
    "AgentLoop",
    "AgentLoopOutcome",
    "AgentLoopPreview",
    "AgentLoopRequest",
]
