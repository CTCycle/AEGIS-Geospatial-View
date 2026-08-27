from __future__ import annotations

from server.common.typing import is_json_array, is_json_object, json_object

import asyncio
import json
import logging
import time
from typing import Any

from server.contracts.geospatial import MapSession

from server.domain.agent.execution import (
    AgentExecutionContext,
    AgentToolLoopRequest,
    AgentToolLoopResult,
)
from server.services.agent.tool_registry import ToolRegistry
from server.domain.agent.runtime import canonical_call_fingerprint
from server.services.llm.factory import LLMFactory
from server.services.llm.context_budget import prepare_request
from server.services.llm.types import (
    LLMRequest,
    LLMToolCall,
    LLMToolResult,
)

LOGGER = logging.getLogger(__name__)

###############################################################################
class NativeToolLoop:

    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        provider_factory: LLMFactory,
        tool_registry: ToolRegistry,
        max_iterations: int = 8,
        max_parallel_tool_calls: int = 8,
        max_tool_result_chars: int = 12000,
        tool_timeout_seconds: int = 30,
        max_model_calls: int = 6,
        max_tool_calls: int = 12,
        max_state_transitions: int = 16,
        max_run_seconds: float = 180.0,
        max_no_progress_steps: int = 2,
    ) -> None:
        self.provider_factory = provider_factory
        self.tool_registry = tool_registry
        self.max_iterations = max_iterations
        self.max_parallel_tool_calls = max_parallel_tool_calls
        self.max_tool_result_chars = max_tool_result_chars
        self.tool_timeout_seconds = tool_timeout_seconds
        self.max_model_calls = max_model_calls
        self.max_tool_calls = max_tool_calls
        self.max_state_transitions = max_state_transitions
        self.max_run_seconds = max_run_seconds
        self.max_no_progress_steps = max_no_progress_steps
        self.last_context_usages: list[dict[str, Any]] = []

    # -------------------------------------------------------------------------
    async def run(self, request: AgentToolLoopRequest) -> AgentToolLoopResult:
        provider = self.provider_factory.get_provider(request.provider)
        messages = list(request.messages)
        working_state = {
            "role": "system",
            "content": "WORKING_STATE (replaceable): "
            + json.dumps(
                {
                    "parsed_request": request.context.parsed_request,
                    "map_state": request.context.map_state,
                    "policy_constraints": request.context.policy_constraints,
                    "completed_tool_results": [],
                },
                default=str,
            ),
        }
        messages.insert(1, working_state)
        all_calls: list[LLMToolCall] = []
        all_results: list[LLMToolResult] = []
        fingerprints: set[str] = set()
        duplicate_tool_calls = 0
        no_progress_steps = 0
        started_run = time.perf_counter()
        simple_run = str(request.context.metadata.get("complexity") or "").lower() == "simple"
        model_budget = 2 if simple_run else self.max_model_calls
        tool_budget = 2 if simple_run else self.max_tool_calls
        transition_budget = 6 if simple_run else self.max_state_transitions
        self.last_context_usages = []

        for iteration in range(1, self.max_iterations + 1):
            if (
                iteration > model_budget
                or len(all_calls) >= tool_budget
                or iteration + len(all_results) > transition_budget
                or time.perf_counter() - started_run > (45.0 if simple_run else self.max_run_seconds)
            ):
                return AgentToolLoopResult(
                    final_text="The agent reached its execution budget before completing the request.",
                    tool_calls=all_calls,
                    tool_results=all_results,
                    iterations=iteration - 1,
                    stopped_reason="budget_exhausted",
                    map_session=self._extract_map_session(all_results),
                    model_calls=iteration - 1,
                    duplicate_tool_calls=duplicate_tool_calls,
                    no_progress_steps=no_progress_steps,
                )
            working_state["content"] = "WORKING_STATE (replaceable): " + json.dumps(
                {
                    "parsed_request": request.context.parsed_request,
                    "map_state": request.context.map_state,
                    "policy_constraints": request.context.policy_constraints,
                    "completed_tool_results": [
                        {"tool": result.name, "ok": not result.is_error, "error": result.error}
                        for result in all_results
                    ],
                },
                default=str,
            )
            LOGGER.info(
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
                        messages=messages,
                        tools=request.tools,
                        tool_choice="auto",
                        temperature=request.temperature,
                        metadata={"max_tokens": request.max_tokens}
                        if request.max_tokens is not None
                        else {},
                    ),
                    provider=request.provider,
                )
                messages = list(llm_request.messages)
                working_state = messages[1]
                response = provider.chat(llm_request)
                usage = getattr(provider, "last_context_usage", None)
                if is_json_object(usage):
                    self.last_context_usages.append(dict(usage))
            except Exception as exc:
                LOGGER.exception("tool_loop_failed provider=%s model=%s", request.provider, request.model)
                category = getattr(exc, "category", None)
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
                return AgentToolLoopResult(
                    final_text=final_text,
                    tool_calls=all_calls,
                    tool_results=all_results,
                    iterations=iteration,
                    stopped_reason="provider_error",
                    map_session=self._extract_map_session(all_results),
                    model_calls=iteration,
                    duplicate_tool_calls=duplicate_tool_calls,
                    no_progress_steps=no_progress_steps,
                    failure_category=category,
                    failure_detail=detail,
                )

            if not response.tool_calls:
                return AgentToolLoopResult(
                    final_text=response.content,
                    tool_calls=all_calls,
                    tool_results=all_results,
                    iterations=iteration,
                    stopped_reason="final",
                    map_session=self._extract_map_session(all_results),
                    model_calls=iteration,
                    duplicate_tool_calls=duplicate_tool_calls,
                    no_progress_steps=no_progress_steps,
                )

            tool_calls = response.tool_calls[: min(self.max_parallel_tool_calls, tool_budget - len(all_calls))]
            all_calls.extend(tool_calls)
            raw_output = response.raw.get("output") if is_json_object(response.raw) else None
            if is_json_array(raw_output):
                # Responses providers require every output item (including
                # reasoning/function-call items) to be retained on the next
                # request.  Other providers continue using the portable
                # assistant/tool-message representation below.
                messages.extend(
                    item for item in raw_output if is_json_object(item)
                )
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
                fingerprint = canonical_call_fingerprint(call.name, call.arguments)
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
                results_list.append(await self._execute_tool_call(call, request.context, iteration))
            results = results_list
            all_results.extend(results)
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
                    map_session=self._extract_map_session(all_results),
                    model_calls=iteration,
                    duplicate_tool_calls=duplicate_tool_calls,
                    no_progress_steps=no_progress_steps,
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
            stopped_reason="max_iterations",
            map_session=self._extract_map_session(all_results),
            model_calls=self.max_iterations,
            duplicate_tool_calls=duplicate_tool_calls,
            no_progress_steps=no_progress_steps,
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def _extract_map_session(
        results: list[LLMToolResult],
    ) -> MapSession | None:
        for result in reversed(results):
            content = result.content if is_json_object(result.content) else None
            if content is None:
                continue
            data = content.get("data")
            if not is_json_object(data):
                continue
            operation = data.get("operation")
            if operation != "map_session_created":
                continue
            ms_raw = data.get("map_session")
            if is_json_object(ms_raw):
                try:
                    return MapSession.model_validate(ms_raw)
                except Exception:
                    LOGGER.warning("Failed to validate MapSession from tool result", exc_info=True)
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
            LOGGER.info(
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
        try:
            envelope = await asyncio.wait_for(
                self.tool_registry.execute_native_tool(call.name, call.arguments, context),
                timeout=self.tool_timeout_seconds,
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
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        ok = bool(envelope_payload.get("ok"))
        LOGGER.info(
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
            error=str(error_payload.get("message")) if error_payload.get("message") else None,
        )

    # -------------------------------------------------------------------------
    def _truncate_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        serialized = json.dumps(payload, ensure_ascii=True, default=str)
        if len(serialized) <= self.max_tool_result_chars:
            return payload
        return {
            "ok": payload.get("ok", False),
            "data": {
                "truncated": True,
                "original_size": len(serialized),
                "content_preview": serialized[: self.max_tool_result_chars],
                "next_cursor": self._extract_next_cursor(payload),
            },
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
        if is_json_array(allowed) and allowed and call.name not in set(map(str, allowed)):
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
            if (
                not is_json_array(allowed_providers)
                or provider_id not in set(map(str, allowed_providers))
            ):
                return f"Provider '{provider_id}' is not allowed by policy constraints."
        return None
