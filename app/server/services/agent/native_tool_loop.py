from __future__ import annotations

from server.common.typing import is_json_array, is_json_object, json_object

import asyncio
import json
import logging
import time
from datetime import UTC, datetime
from contextlib import nullcontext as _nullcontext
from collections.abc import Awaitable, Callable
from typing import Any, Literal, cast

from server.contracts.geospatial import MapSession

from server.domain.agent.execution import (
    AgentExecutionContext,
    AgentToolLoopRequest,
    AgentToolLoopResult,
)
from server.domain.agent.pipeline import ToolPlanStep
from server.services.agent.tool_registry import ToolRegistry
from server.services.agent.completion import CompletionEvaluator
from server.services.agent.tool_plan_executor import ToolPlanExecutor
from server.domain.agent.runtime import canonical_call_fingerprint
from server.prompts.agent import build_working_state_message
from server.services.llm.factory import LLMFactory
from server.services.llm.context_budget import prepare_request
from server.services.llm.context_profile_resolver import ModelContextProfileResolver
from server.services.llm.request_deadline import REQUEST_DEADLINE_METADATA_KEY
from server.services.llm.types import (
    LLMRequest,
    LLMResult,
    LLMToolCall,
    LLMToolResult,
)

LOGGER = logging.getLogger(__name__)

###############################################################################
class NativeToolLoop:

    # -------------------------------------------------------------------------
    def supports_native_tools(self, provider_name: str, model: str) -> bool:
        """Return the provider's explicit native-tool capability decision.

        ``None`` is treated as usable because several provider adapters only
        learn capabilities during a live probe.  A provider that explicitly
        reports ``False`` is routed to deterministic execution instead.
        """

        provider = self.provider_factory.get_provider(provider_name)
        supports = provider.supports_tools(model)
        return supports is not False

    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        provider_factory: LLMFactory,
        tool_registry: ToolRegistry,
        context_profile_resolver: ModelContextProfileResolver | None = None,
        max_parallel_tool_calls: int = 8,
        max_tool_result_chars: int = 4096,
        tool_timeout_seconds: int = 45,
        max_iterations: int = 12,
        max_model_calls: int = 10,
        max_tool_calls: int = 20,
        max_state_transitions: int = 32,
        max_run_seconds: float = 300.0,
        max_no_progress_steps: int = 3,
    ) -> None:
        self.provider_factory = provider_factory
        self.tool_registry = tool_registry
        self.context_profile_resolver = context_profile_resolver
        self.max_iterations = max_iterations
        self.max_parallel_tool_calls = max_parallel_tool_calls
        self.max_tool_result_chars = max_tool_result_chars
        self.tool_timeout_seconds = tool_timeout_seconds
        self.max_model_calls = max_model_calls
        self.max_tool_calls = max_tool_calls
        self.max_state_transitions = max_state_transitions
        self.max_run_seconds = max_run_seconds
        self.max_no_progress_steps = max_no_progress_steps

    # -------------------------------------------------------------------------
    async def run(self, request: AgentToolLoopRequest) -> AgentToolLoopResult:
        context = request.context
        provider = self.provider_factory.get_provider(request.provider)
        messages = list(request.messages)
        current_tools = list(request.tools)
        working_state = build_working_state_message(
            parsed_request=context.parsed_request,
            map_state=context.map_state,
            policy_constraints=context.policy_constraints,
            completed_tool_results=[],
            evidence_summaries=list(
                context.metadata.get("prior_evidence_summaries") or []
            ),
        )
        messages.insert(1, working_state)
        all_calls: list[LLMToolCall] = []
        all_results: list[LLMToolResult] = []
        fingerprints: set[str] = set()
        duplicate_tool_calls = 0
        no_progress_steps = 0
        simple_run = (
            str(context.metadata.get("complexity") or "").lower() == "simple"
        )
        model_budget = min(self.max_model_calls, 10 if not simple_run else 4)
        tool_budget = min(self.max_tool_calls, 20 if not simple_run else 6)
        transition_budget = min(self.max_state_transitions, 32 if not simple_run else 10)
        premature_stop_proposals = 0
        context_usages: list[dict[str, Any]] = []
        execution_budget = context.execution_budget
        run_deadline = (
            execution_budget.deadline_monotonic
            if execution_budget is not None
            else time.monotonic() + (45.0 if simple_run else self.max_run_seconds)
        )

        def record_context_usage(raw_usage: object) -> None:
            if not is_json_object(raw_usage):
                return
            usage = dict(raw_usage)
            context_usages.append(usage)
            if context.execution_budget is not None:
                context.execution_budget.record_context_allocation(
                    {
                        "phase": "native_loop",
                        "model": request.model,
                        **usage,
                    }
                )
            if request.context_usage_callback is not None:
                request.context_usage_callback(usage)

        for iteration in range(1, self.max_iterations + 1):
            iteration_started = time.perf_counter()
            if (
                iteration > model_budget
                or len(all_calls) >= tool_budget
                or iteration + len(all_results) > transition_budget
                or time.monotonic() > run_deadline
                or (
                    execution_budget is not None
                    and execution_budget.remaining_seconds() <= 0.0
                )
            ):
                if execution_budget is not None:
                    execution_budget.terminal_reason = "agent_loop_budget_exhausted"
                return AgentToolLoopResult(
                    final_text="The agent reached its execution budget before completing the request.",
                    tool_calls=all_calls,
                    tool_results=all_results,
                    iterations=iteration - 1,
                    stopped_reason=(
                        "run_deadline_exhausted"
                        if time.monotonic() > run_deadline
                        else "tool_budget_exhausted"
                    ),
                    map_session=self._extract_map_session(all_results, context),
                    model_calls=iteration - 1,
                    duplicate_tool_calls=duplicate_tool_calls,
                    no_progress_steps=no_progress_steps,
                    context_usages=list(context_usages),
                )
            working_state = build_working_state_message(
                parsed_request=context.parsed_request,
                map_state=context.map_state,
                policy_constraints=context.policy_constraints,
                completed_tool_results=[
                    self._result_observation(result)
                    for result in all_results
                ],
                evidence_summaries=list(
                    context.metadata.get("prior_evidence_summaries") or []
                )
                + [
                    self._result_observation(result)
                    for result in all_results
                    if self._result_observation(result).get("evidence_ref")
                ],
            )
            messages[1] = working_state
            if request.tool_resolver is not None:
                current_tools = request.tool_resolver(context, all_results)
                context.policy_constraints["available_tools"] = [
                item.name for item in current_tools
            ]
                context.policy_constraints["tool_exposure_reasons"] = dict(
                    context.metadata.get("tool_exposure_reasons") or {}
            )
            LOGGER.debug(
                "tool_loop_started provider=%s model=%s iteration=%s",
                request.provider,
                request.model,
                iteration,
            )
            try:
                llm_request = prepare_request(
                    LLMRequest(
                        model=request.model,
                        provider=request.provider,
                        messages=list(messages),
                        tools=current_tools,
                        tool_choice="auto",
                        temperature=request.temperature,
                        provider_session_id=(
                            request.provider_session_id
                            or context.conversation_id
                        ),
                        metadata={
                            **(
                                self.context_profile_resolver.request_metadata(
                                    request.provider,
                                    request.model,
                                )
                                if self.context_profile_resolver is not None
                                else {}
                            ),
                            **(
                                {"max_tokens": request.max_tokens}
                                if request.max_tokens is not None
                                else {}
                            ),
                            "application_input_token_ceiling": 64_000,
                            "context_phase": "native_loop",
                            REQUEST_DEADLINE_METADATA_KEY: run_deadline,
                        },
                    ),
                    provider=request.provider,
                )
                messages = list(llm_request.messages)
                working_state = messages[1]
                if execution_budget is not None:
                    execution_budget.record_model_call()
                model_timeout = float(
                    context.metadata.get("native_model_call_seconds", 60.0)
                    or 60.0
                )
                if execution_budget is not None:
                    model_timeout = min(
                        model_timeout, execution_budget.remaining_seconds()
                    )
                with (
                    execution_budget.observe(
                        "agent_model_call",
                        metadata={
                            "iteration": iteration,
                            "provider": request.provider,
                            "model": request.model,
                        },
                    )
                    if execution_budget is not None
                    else _nullcontext()
                ):
                    async_chat = getattr(provider, "achat", None)
                    if callable(async_chat):
                        response = await asyncio.wait_for(
                            cast(
                                Callable[[LLMRequest], Awaitable[LLMResult]], async_chat
                            )(llm_request),
                            timeout=max(0.001, model_timeout),
                        )
                    else:
                        # Only detached/test adapters should reach this
                        # compatibility branch. Production OpenCode/DeepSeek
                        # providers implement achat with a cancellable client.
                        response = await asyncio.wait_for(
                            asyncio.to_thread(provider.chat, llm_request),
                            timeout=max(0.001, model_timeout),
                        )
                record_context_usage(getattr(response, "context_usage", None))
            except TimeoutError as exc:
                timeout_origin = (
                    "application_deadline"
                    if execution_budget is not None
                    and execution_budget.remaining_seconds() <= 0.0
                    else "provider_transport"
                )
                if execution_budget is not None:
                    execution_budget.terminal_reason = (
                        "run_deadline_exhausted"
                        if timeout_origin == "application_deadline"
                        else "provider_error"
                    )
                return AgentToolLoopResult(
                    final_text=(
                        "The agent provider did not return a native decision before "
                        "the bounded model-call deadline."
                    ),
                    tool_calls=all_calls,
                    tool_results=all_results,
                    iterations=iteration,
                    stopped_reason=(
                        "run_deadline_exhausted"
                        if timeout_origin == "application_deadline"
                        else "provider_error"
                    ),
                    map_session=self._extract_map_session(all_results, context),
                    model_calls=iteration,
                    duplicate_tool_calls=duplicate_tool_calls,
                    no_progress_steps=no_progress_steps,
                    failure_category="provider_api",
                    failure_detail=str(exc) or "Native model decision timed out.",
                    timeout_origin=timeout_origin,
                    context_usages=list(context_usages),
                )
            except Exception as exc:
                category = getattr(exc, "category", None)
                if category in {
                    "context_limit",
                    "model_capability",
                    "schema_definition",
                    "provider_api",
                }:
                    LOGGER.warning(
                        "tool_loop_failed category=%s provider=%s model=%s",
                        category,
                        request.provider,
                        request.model,
                    )
                else:
                    LOGGER.exception(
                        "tool_loop_failed provider=%s model=%s",
                        request.provider,
                        request.model,
                    )
                detail = str(getattr(exc, "detail", None) or exc)
                if category == "context_limit":
                    final_text = (
                        "The agent stopped because the selected model context limit was reached. "
                        "Older context was compacted where possible, but the required tool state still did not fit."
                    )
                elif category == "model_capability":
                    final_text = (
                        "The selected model explicitly rejected native tool calling. "
                        "Choose a model/provider with tool support or retry after checking its live capabilities."
                    )
                elif category == "schema_definition":
                    final_text = (
                        "The agent tool definition was invalid before the provider request was sent. "
                        "This is an application schema issue."
                    )
                elif category == "provider_api":
                    final_text = (
                        "The agent provider failed while executing the tool loop. "
                        "Check the provider response, credentials, rate limit, or network and retry."
                    )
                else:
                    final_text = "The agent tool loop failed before it could complete the request."
                if execution_budget is not None:
                    execution_budget.terminal_reason = "provider_error"
                record_context_usage(getattr(exc, "context_usage", None))
                return AgentToolLoopResult(
                    final_text=final_text,
                    tool_calls=all_calls,
                    tool_results=all_results,
                    iterations=iteration,
                    stopped_reason="provider_error",
                    map_session=self._extract_map_session(all_results, context),
                    model_calls=iteration,
                    duplicate_tool_calls=duplicate_tool_calls,
                    no_progress_steps=no_progress_steps,
                    failure_category=category,
                    failure_detail=detail,
                    timeout_origin=getattr(exc, "timeout_origin", None),
                    context_usages=list(context_usages),
                )

            if not response.tool_calls:
                stop_reason = self._evaluate_textual_stop(
                    response.content,
                    context,
                    all_results,
                    current_tools,
                )
                if stop_reason in {"goal_satisfied", "awaiting_render", "clarification_required", "insufficient_evidence"}:
                    self._record_iteration_trace(
                        context,
                        iteration=iteration,
                        available_tools=current_tools,
                        selected_tool=None,
                        result_status="textual_stop",
                        results=all_results,
                        started=iteration_started,
                        stopping_evaluation={"reason": stop_reason},
                    )
                    return AgentToolLoopResult(
                        final_text=response.content,
                        tool_calls=all_calls,
                        tool_results=all_results,
                        iterations=iteration,
                        stopped_reason=stop_reason,
                        map_session=self._extract_map_session(all_results, context),
                        model_calls=iteration,
                        duplicate_tool_calls=duplicate_tool_calls,
                        no_progress_steps=no_progress_steps,
                        context_usages=list(context_usages),
                    )
                premature_stop_proposals += 1
                if premature_stop_proposals >= 2:
                    self._record_iteration_trace(
                        context,
                        iteration=iteration,
                        available_tools=current_tools,
                        selected_tool=None,
                        result_status="no_progress",
                        results=all_results,
                        started=iteration_started,
                        stopping_evaluation={"reason": "no_progress"},
                    )
                    return AgentToolLoopResult(
                        final_text="The agent stopped before satisfying the request requirements.",
                        tool_calls=all_calls,
                        tool_results=all_results,
                        iterations=iteration,
                        stopped_reason="no_progress",
                        map_session=self._extract_map_session(all_results, context),
                        model_calls=iteration,
                        duplicate_tool_calls=duplicate_tool_calls,
                        no_progress_steps=no_progress_steps + 1,
                        context_usages=list(context_usages),
                    )
                messages.append({"role": "assistant", "content": response.content or ""})
                messages.append(
                    {
                        "role": "system",
                        "content": "The response proposed a stop, but required tasks remain pending. Continue with one allowed native tool or state a typed clarification/error.",
                    }
                )
                continue

            tool_calls = response.tool_calls[
                : min(self.max_parallel_tool_calls, tool_budget - len(all_calls))
            ]
            all_calls.extend(tool_calls)
            raw_output = (
                response.raw.get("output") if is_json_object(response.raw) else None
            )
            if is_json_array(raw_output):
                # Responses providers require every output item (including
                # reasoning/function-call items) to be retained on the next
                # request.  Other providers continue using the portable
                # assistant/tool-message representation below.
                messages.extend(item for item in raw_output if is_json_object(item))
            else:
                messages.append(
                    {
                        "role": "assistant",
                        "content": response.content or None,
                        "tool_calls": [
                            {
                                "id": call.id,
                                "name": call.name,
                                "arguments": call.arguments,
                            }
                            for call in tool_calls
                        ],
                    }
                )
            results_list: list[LLMToolResult] = []
            for call in tool_calls:
                bound_call, bind_error = self._bind_geospatial_call(call, context)
                if bind_error is not None:
                    results_list.append(
                        LLMToolResult(
                            tool_call_id=call.id,
                            name=call.name,
                            content={
                                "ok": False,
                                "data": None,
                                "error": {
                                    "code": bind_error[0],
                                    "message": bind_error[1],
                                },
                                "metadata": {},
                            },
                            is_error=True,
                            error=bind_error[1],
                        )
                    )
                    continue
                fingerprint = self._call_fingerprint(bound_call, context)
                if fingerprint in fingerprints:
                    duplicate_tool_calls += 1
                    results_list.append(
                        LLMToolResult(
                            tool_call_id=call.id,
                            name=call.name,
                            content={
                                "ok": False,
                                "data": None,
                                "error": {
                                    "code": "duplicate_tool_call",
                                    "message": "This canonical tool call already completed in the run.",
                                },
                                "metadata": {},
                            },
                            is_error=True,
                            error="Duplicate canonical tool call.",
                        )
                    )
                    continue
                fingerprints.add(fingerprint)
                results_list.append(
                    await self._execute_tool_call(bound_call, context, iteration)
                )
            results = results_list
            all_results.extend(results)
            self._record_iteration_trace(
                context,
                iteration=iteration,
                available_tools=current_tools,
                selected_tool=tool_calls[0].name if tool_calls else None,
                result_status="failed" if results and all(item.is_error for item in results) else "available",
                results=results,
                started=iteration_started,
                stopping_evaluation=None,
            )
            if results and all(result.is_error for result in results):
                no_progress_steps += 1
            else:
                no_progress_steps = 0
            if no_progress_steps >= self.max_no_progress_steps:
                return AgentToolLoopResult(
                    final_text="The agent stopped after repeated steps produced no progress.",
                    tool_calls=all_calls,
                    tool_results=all_results,
                    iterations=iteration,
                    stopped_reason="no_progress",
                    map_session=self._extract_map_session(all_results, context),
                    model_calls=iteration,
                    duplicate_tool_calls=duplicate_tool_calls,
                    no_progress_steps=no_progress_steps,
                    context_usages=list(context_usages),
                )
            for result in results:
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": result.tool_call_id,
                        "name": result.name,
                        "content": self._stringify_tool_result(result),
                    }
                )

        return AgentToolLoopResult(
            final_text="The agent reached the maximum number of tool iterations.",
            tool_calls=all_calls,
            tool_results=all_results,
            iterations=self.max_iterations,
            stopped_reason="tool_budget_exhausted",
            map_session=self._extract_map_session(all_results, context),
            model_calls=self.max_iterations,
            duplicate_tool_calls=duplicate_tool_calls,
            no_progress_steps=no_progress_steps,
            context_usages=list(context_usages),
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def _result_observation(result: LLMToolResult) -> dict[str, Any]:
        content = result.content if is_json_object(result.content) else {}
        data = content.get("data") if is_json_object(content) else None
        observation: dict[str, Any] = {
            "tool": result.name,
            "ok": not result.is_error,
            "error": result.error,
        }
        if is_json_object(data):
            for key in (
                "evidence_ref",
                "evidence_refs",
                "status",
                "summary",
                "provenance",
                "map_eligibility",
                "state_changes",
                "pagination",
            ):
                if key in data:
                    observation[key] = data[key]
        return observation

    @staticmethod
    def _record_iteration_trace(
        context: AgentExecutionContext,
        *,
        iteration: int,
        available_tools: list[Any],
        selected_tool: str | None,
        result_status: str,
        results: list[LLMToolResult],
        started: float,
        stopping_evaluation: dict[str, Any] | None,
    ) -> None:
        budget = context.execution_budget
        if budget is None:
            return
        evidence_refs: list[str] = []
        state_changes: list[dict[str, Any]] = []
        capability_id: str | None = None
        for result in results:
            content = result.content if is_json_object(result.content) else {}
            data = content.get("data") if is_json_object(content) else None
            if not is_json_object(data):
                continue
            ref = data.get("evidence_ref")
            if isinstance(ref, str) and ref:
                evidence_refs.append(ref)
            refs = data.get("evidence_refs")
            if is_json_array(refs):
                evidence_refs.extend(str(item) for item in refs if str(item))
            state = data.get("state_changes")
            if is_json_array(state):
                state_changes.extend(
                    item for item in state if is_json_object(item)
                )
            summary = data.get("summary")
            if is_json_object(summary) and summary.get("capability_id"):
                capability_id = str(summary["capability_id"])
        budget.record_iteration(
            {
                "iteration": iteration,
                "execution_mode": str(context.metadata.get("execution_mode") or "native"),
                "available_tools": [str(getattr(item, "name", "")) for item in available_tools],
                "tool_exposure_reasons": dict(context.metadata.get("tool_exposure_reasons") or {}),
                "selected_tool": selected_tool,
                "capability_id": capability_id,
                "started_at": datetime.now(UTC).isoformat(),
                "duration_ms": max(0, int((time.perf_counter() - started) * 1000)),
                "result_status": result_status,
                "evidence_refs": list(dict.fromkeys(evidence_refs)),
                "state_changes": state_changes,
                "pending_requirements": [
                    str(item)
                    for item in cast(
                        list[Any], context.metadata.get("completion_requirements") or []
                    )
                ],
                "retry_number": int(context.metadata.get("last_retry_number") or 0),
                "context_usage": {},
                "stopping_evaluation": stopping_evaluation,
            }
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def _call_fingerprint(call: LLMToolCall, context: AgentExecutionContext) -> str:
        """Include canonical scope in duplicate detection for native calls."""

        canonical = context.canonical_request
        target_id = None
        analysis_scope = None
        temporal: dict[str, Any] = {}
        if canonical is not None:
            target = canonical.primary_target
            target_id = target.target_id if target is not None else None
            if canonical.spatial_constraints:
                analysis_scope = canonical.spatial_constraints[0].analysis_scope
            temporal = {
                "mode": canonical.temporal_constraints.mode,
                "start_time_iso": canonical.temporal_constraints.start_time_iso,
                "end_time_iso": canonical.temporal_constraints.end_time_iso,
            }
        return canonical_call_fingerprint(
            call.name,
            {
                "arguments": call.arguments,
                "plan_step_id": context.metadata.get("native_bound_step_id"),
                "target_id": target_id,
                "analysis_scope": analysis_scope,
                "temporal": temporal,
            },
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def _bind_geospatial_call(
        call: LLMToolCall,
        context: AgentExecutionContext,
    ) -> tuple[LLMToolCall, tuple[str, str] | None]:
        """Bind a model capability choice to the next canonical plan step.

        The model may select an allowlisted capability, but it cannot provide
        application-owned target IDs or provider arguments.  The deterministic
        planner remains the sole owner of those values.
        """

        context.metadata["native_bound_step_id"] = None
        if call.name != "execute_geospatial_capability":
            return call, None
        capability_id = str(call.arguments.get("capability_id") or "").strip()
        raw_steps = context.metadata.get("tool_plan_steps")
        if not is_json_array(raw_steps):
            return call, None
        completed_raw = context.metadata.get("native_bound_plan_step_ids")
        completed: set[str] = (
            {str(item) for item in completed_raw}
            if is_json_array(completed_raw)
            else set()
        )
        for raw_step in raw_steps:
            if not is_json_object(raw_step):
                continue
            step_id = str(raw_step.get("step_id") or "").strip()
            if not step_id or step_id in completed:
                continue
            if str(raw_step.get("tool_name") or "") != call.name:
                continue
            planned_capability = str(raw_step.get("capability_id") or "").strip()
            if planned_capability != capability_id:
                continue
            raw_arguments = raw_step.get("arguments")
            planned_arguments = (
                json_object(json_object(raw_arguments).get("arguments"))
                if is_json_object(raw_arguments)
                else {}
            )
            if not planned_arguments and raw_arguments not in ({}, None):
                return call, (
                    "planning_target_unbound",
                    f"Deterministic plan step '{step_id}' has no validated arguments.",
                )
            completed.add(step_id)
            context.metadata["native_bound_plan_step_ids"] = sorted(completed)
            context.metadata["native_bound_step_id"] = step_id
            target_id = str(raw_step.get("target_id") or "").strip() or None
            if target_id is not None:
                context.metadata["target_id"] = target_id
            return (
                LLMToolCall(
                    id=call.id,
                    name=call.name,
                    arguments={
                        "capability_id": planned_capability,
                        "arguments": planned_arguments,
                    },
                ),
                None,
            )
        return call, (
            "capability_not_planned",
            f"Capability '{capability_id}' has no unexecuted deterministic plan step.",
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def _extract_map_session(
        results: list[LLMToolResult],
        context: AgentExecutionContext | None = None,
    ) -> MapSession | None:
        if context is not None:
            prepared = context.metadata.get("prepared_map_session")
            if is_json_object(prepared):
                try:
                    return MapSession.model_validate(prepared)
                except Exception:  # noqa: BLE001
                    LOGGER.warning(
                        "Failed to validate prepared MapSession from execution context",
                        exc_info=True,
                    )
        for result in reversed(results):
            content = result.content if is_json_object(result.content) else None
            if content is None:
                continue
            data = content.get("data")
            if not is_json_object(data):
                continue
            operation = data.get("operation")
            summary = data.get("summary")
            if operation is None and is_json_object(summary):
                operation = summary.get("operation")
            if operation != "map_session_created":
                continue
            ms_raw = data.get("map_session")
            if ms_raw is None and is_json_object(summary):
                ms_raw = summary.get("map_session")
            if (
                is_json_object(ms_raw)
                and is_json_object(ms_raw.get("resolved_location"))
                and is_json_object(ms_raw.get("overlay_collection"))
                and is_json_array(ms_raw["overlay_collection"].get("instances"))
            ):
                try:
                    return MapSession.model_validate(ms_raw)
                except Exception:
                    LOGGER.warning(
                        "Failed to validate MapSession from tool result", exc_info=True
                    )
        return None

    # -------------------------------------------------------------------------
    @staticmethod
    def _evaluate_textual_stop(
        content: str,
        context: AgentExecutionContext,
        results: list[LLMToolResult],
        available_tools: list[Any],
    ) -> Literal[
        "goal_satisfied",
        "awaiting_render",
        "clarification_required",
        "insufficient_evidence",
    ] | None:
        """Treat text as a proposal and compare it with durable requirements."""

        _ = content
        metadata = context.metadata or {}
        missing_fields = metadata.get("clarification_required")
        map_session = NativeToolLoop._extract_map_session(results, context)
        evidence_refs = [
            str(item)
            for item in cast(list[Any], metadata.get("evidence_refs") or [])
        ]
        missing_fields_list = (
            cast(list[Any], missing_fields) if isinstance(missing_fields, list) else []
        )
        available_names = [
            str(getattr(item, "name", ""))
            for item in available_tools
        ]
        evaluation = CompletionEvaluator.evaluate_proposed_stop(
            canonical_request=context.canonical_request,
            presentation_required=bool(metadata.get("presentation_required")),
            map_prepared=map_session is not None,
            evidence_refs=evidence_refs,
            available_tools=available_names,
            clarification_required=bool(missing_fields_list),
            provider_error=False,
        )
        if evaluation.satisfied:
            return "goal_satisfied"
        if evaluation.reason == "clarification_required":
            return "clarification_required"
        if evaluation.reason == "awaiting_render":
            return "awaiting_render"
        if evaluation.reason == "insufficient_evidence":
            return "insufficient_evidence"
        return None

    # -------------------------------------------------------------------------
    async def _execute_tool_call(
        self,
        call: LLMToolCall,
        context: AgentExecutionContext,
        iteration: int,
    ) -> LLMToolResult:
        started = time.perf_counter()
        rejection = self._policy_rejection(call, context)
        if rejection is not None:
            LOGGER.debug(
                "tool_call_rejected tool=%s iteration=%s reason=%s",
                call.name,
                iteration,
                rejection,
            )
            return LLMToolResult(
                tool_call_id=call.id,
                name=call.name,
                content={
                    "ok": False,
                    "data": None,
                    "error": {"code": "tool_rejected", "message": rejection},
                    "metadata": {},
                },
                is_error=True,
                error=rejection,
            )
        execution_budget = context.execution_budget
        idle_timeout = float(
            context.metadata.get("tool_idle_seconds", self.tool_timeout_seconds)
            or self.tool_timeout_seconds
        )
        absolute_timeout = float(
            context.metadata.get("tool_absolute_seconds", 90.0) or 90.0
        )
        timeout = min(idle_timeout, absolute_timeout)
        if execution_budget is not None:
            timeout = min(timeout, execution_budget.remaining_seconds())
        retry_number = 0
        retryable_codes = {
            "tool_timeout",
            "provider_timeout",
            "rate_limited",
            "provider_unavailable",
        }
        while True:
            if execution_budget is not None:
                execution_budget.record_tool_call()
            try:
                with (
                    execution_budget.observe(
                        "tool_execution",
                        metadata={
                            "tool": call.name,
                            "iteration": iteration,
                            "retry_number": retry_number,
                            "idle_deadline_seconds": idle_timeout,
                            "absolute_deadline_seconds": absolute_timeout,
                        },
                    )
                    if execution_budget is not None
                    else _nullcontext()
                ):
                    envelope = await asyncio.wait_for(
                        self.tool_registry.execute_native_tool(
                            call.name, call.arguments, context
                        ),
                        timeout=max(0.001, timeout),
                    )
            except TimeoutError:
                envelope_payload = {
                    "ok": False,
                    "data": None,
                    "error": {
                        "code": "tool_timeout",
                        "message": f"Tool '{call.name}' timed out.",
                    },
                    "metadata": {},
                }
            else:
                envelope_payload = envelope.to_dict()
            error = json_object(envelope_payload.get("error"))
            error_code = str(error.get("code") or "")
            if (
                envelope_payload.get("ok") is False
                and error_code in retryable_codes
                and retry_number == 0
                and (
                    execution_budget is None
                    or execution_budget.remaining_seconds() > timeout
                )
            ):
                retry_number = 1
                if execution_budget is not None:
                    execution_budget.record_retry()
                continue
            break
        context.metadata["last_retry_number"] = retry_number
        if (
            retry_number
            and execution_budget is not None
            and execution_budget.terminal_reason == "provider_timeout"
        ):
            execution_budget.terminal_reason = None
        self._record_evidence_refs(context, envelope_payload)
        data = envelope_payload.get("data")
        if is_json_object(data):
            candidate = data.get("map_session")
            if candidate is None:
                summary = data.get("summary")
                if is_json_object(summary):
                    candidate = summary.get("map_session")
            if (
                is_json_object(candidate)
                and is_json_object(candidate.get("resolved_location"))
                and is_json_object(candidate.get("overlay_collection"))
                and is_json_array(candidate["overlay_collection"].get("instances"))
            ):
                # Keep the validated map candidate server-side while the model
                # receives only the bounded evidence summary after truncation.
                context.metadata["prepared_map_session"] = dict(candidate)
        # Geometry and viewport validation remains server-owned.  The model
        # receives only the bounded evidence summary; use the full candidate
        # retained in context metadata for the shared typed validator without
        # re-embedding provider payloads in the next model message.
        validation_envelope = envelope_payload
        validation_data = envelope_payload.get("data")
        prepared_candidate = context.metadata.get("prepared_map_session")
        if (
            is_json_object(validation_data)
            and "map_session" not in validation_data
            and is_json_object(prepared_candidate)
        ):
            validation_envelope = {
                **envelope_payload,
                "data": {**validation_data, "map_session": prepared_candidate},
            }
        validation_error = self._validate_geospatial_tool_output(
            call, context, validation_envelope
        )
        if validation_error is not None:
            envelope_payload = {
                **envelope_payload,
                "ok": False,
                "error": {
                    "code": "invalid_tool_output",
                    "message": validation_error,
                },
            }
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        ok = bool(envelope_payload.get("ok"))
        LOGGER.debug(
            "tool_call_executed tool=%s iteration=%s success=%s latency_ms=%s",
            call.name,
            iteration,
            ok,
            elapsed_ms,
        )
        content = self._truncate_payload(envelope_payload)
        error_payload = json_object(envelope_payload.get("error"))
        return LLMToolResult(
            tool_call_id=call.id,
            name=call.name,
            content=content,
            is_error=not ok,
            error=str(error_payload.get("message"))
            if error_payload.get("message")
            else None,
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def _record_evidence_refs(
        context: AgentExecutionContext,
        envelope: dict[str, Any],
    ) -> None:
        data = envelope.get("data")
        raw_refs = context.metadata.get("evidence_refs")
        refs: list[Any] = raw_refs if is_json_array(raw_refs) else []
        if "evidence_refs" not in context.metadata or not is_json_array(raw_refs):
            context.metadata["evidence_refs"] = refs
        candidates: list[Any] = []
        if is_json_object(data):
            candidates.extend([data.get("evidence_ref"), data.get("evidence_refs")])
            summary = data.get("summary")
            if is_json_object(summary):
                candidates.extend([summary.get("evidence_ref"), summary.get("evidence_refs")])
        for candidate in candidates:
            if isinstance(candidate, str) and candidate and candidate not in refs:
                refs.append(candidate)
            elif is_json_array(candidate):
                for value in candidate:
                    if isinstance(value, str) and value and value not in refs:
                        refs.append(value)

    # -------------------------------------------------------------------------
    @staticmethod
    def _validate_geospatial_tool_output(
        call: LLMToolCall,
        context: AgentExecutionContext,
        envelope: dict[str, Any],
    ) -> str | None:
        """Apply the planned output contract to native geospatial calls too."""

        if call.name != "execute_geospatial_capability" or not bool(envelope.get("ok")):
            return None
        canonical = context.canonical_request
        target_id = str(context.metadata.get("target_id") or "").strip() or None
        analysis_scope: str | None = None
        if canonical is not None:
            target = canonical.target(target_id) if target_id else canonical.primary_target
            if target is not None:
                target_id = target.target_id
                analysis_scope = next(
                    (
                        item.analysis_scope
                        for item in canonical.spatial_constraints
                        if item.target_id == target.target_id
                    ),
                    None,
                )
        capability_id = (
            str(call.arguments.get("capability_id") or "").strip() or None
        )
        step = ToolPlanStep(
            step_id=f"native:{call.id}",
            tool_name=call.name,
            capability_id=capability_id,
            reason="Native geospatial call validated against the canonical request.",
            arguments=dict(call.arguments),
            target_id=target_id,
            analysis_scope=analysis_scope,
        )
        return ToolPlanExecutor.validate_result(
            step,
            envelope.get("data"),
            canonical,
        )

    # -------------------------------------------------------------------------
    def _truncate_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        serialized = json.dumps(payload, ensure_ascii=True, default=str)
        if len(serialized) <= self.max_tool_result_chars:
            return payload
        data = payload.get("data")
        summary: dict[str, Any] = {
            "externalized": True,
            "original_size": len(serialized),
            "keys": sorted(str(key) for key in data) if is_json_object(data) else [],
        }
        if is_json_object(data):
            for key in ("evidence_ref", "evidence_refs", "next_cursor", "status", "operation", "capability_id"):
                if key in data:
                    summary[key] = data[key]
        if "evidence_ref" in payload:
            summary["evidence_ref"] = payload["evidence_ref"]
        return {
            "ok": payload.get("ok", False),
            "data": summary,
            "error": payload.get("error"),
            "metadata": payload.get("metadata", {}),
        }

    # -------------------------------------------------------------------------
    @staticmethod
    def _extract_next_cursor(payload: dict[str, Any]) -> Any | None:
        data = payload.get("data")
        if is_json_object(data):
            return data.get("next_cursor") or data.get("cursor")
        return None

    # -------------------------------------------------------------------------
    @staticmethod
    def _stringify_tool_result(result: LLMToolResult) -> str:
        if isinstance(result.content, str):
            return result.content
        return json.dumps(result.content, ensure_ascii=True, default=str)

    # -------------------------------------------------------------------------
    @staticmethod
    def _policy_rejection(
        call: LLMToolCall,
        context: AgentExecutionContext,
    ) -> str | None:
        constraints = context.policy_constraints or {}
        blocked_patterns = constraints.get("blocked_patterns")
        if blocked_patterns:
            return "Request contains blocked policy patterns."
        allowed = constraints.get("allowed_tool_names")
        if (
            is_json_array(allowed)
            and allowed
            and call.name not in set(map(str, allowed))
        ):
            return f"Tool '{call.name}' is not allowed by policy constraints."
        if call.name == "execute_geospatial_capability":
            capability_id = str(call.arguments.get("capability_id") or "")
            allowed_capabilities = constraints.get("allowed_capability_ids")
            if (
                is_json_array(allowed_capabilities)
                and allowed_capabilities
                and capability_id not in set(map(str, allowed_capabilities))
            ):
                return f"Capability '{capability_id}' is not allowed by policy constraints."
        if call.name == "fetch_geospatial_provider_layers":
            provider_id = str(call.arguments.get("provider_id") or "").lower()
            allowed_providers = constraints.get("allowed_provider_ids")
            if not is_json_array(allowed_providers) or provider_id not in set(
                map(str, allowed_providers)
            ):
                return f"Provider '{provider_id}' is not allowed by policy constraints."
        return None
