from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Literal

from server.services.agent.tool_registry import ToolRegistry
from server.services.llm.factory import LLMFactory
from server.services.llm.types import (
    LLMRequest,
    LLMToolCall,
    LLMToolDefinition,
    LLMToolResult,
)

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class AgentExecutionContext:
    request_id: str | None = None
    session_id: str | None = None
    parsed_request: Any | None = None
    map_state: dict[str, Any] = field(default_factory=dict)
    policy_constraints: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentToolLoopRequest:
    provider: str
    model: str
    messages: list[dict[str, Any]]
    tools: list[LLMToolDefinition]
    temperature: float
    max_tokens: int | None = None
    context: AgentExecutionContext = field(default_factory=AgentExecutionContext)


@dataclass(frozen=True)
class AgentToolLoopResult:
    final_text: str
    tool_calls: list[LLMToolCall]
    tool_results: list[LLMToolResult]
    iterations: int
    stopped_reason: Literal["final", "max_iterations", "provider_error", "tool_error"]


class NativeToolLoop:
    def __init__(
        self,
        *,
        provider_factory: LLMFactory,
        tool_registry: ToolRegistry,
        max_iterations: int = 8,
        max_parallel_tool_calls: int = 8,
        max_tool_result_chars: int = 12000,
        tool_timeout_seconds: int = 30,
    ) -> None:
        self.provider_factory = provider_factory
        self.tool_registry = tool_registry
        self.max_iterations = max_iterations
        self.max_parallel_tool_calls = max_parallel_tool_calls
        self.max_tool_result_chars = max_tool_result_chars
        self.tool_timeout_seconds = tool_timeout_seconds

    async def run(self, request: AgentToolLoopRequest) -> AgentToolLoopResult:
        provider = self.provider_factory.get_agent_provider(request.provider)
        messages = list(request.messages)
        all_calls: list[LLMToolCall] = []
        all_results: list[LLMToolResult] = []

        for iteration in range(1, self.max_iterations + 1):
            LOGGER.info(
                "tool_loop_started provider=%s model=%s iteration=%s",
                request.provider,
                request.model,
                iteration,
            )
            try:
                response = provider.chat(
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
                    )
                )
            except Exception as exc:
                LOGGER.exception("tool_loop_failed provider=%s model=%s", request.provider, request.model)
                return AgentToolLoopResult(
                    final_text=str(exc),
                    tool_calls=all_calls,
                    tool_results=all_results,
                    iterations=iteration,
                    stopped_reason="provider_error",
                )

            if not response.tool_calls:
                return AgentToolLoopResult(
                    final_text=response.content,
                    tool_calls=all_calls,
                    tool_results=all_results,
                    iterations=iteration,
                    stopped_reason="final",
                )

            tool_calls = response.tool_calls[: self.max_parallel_tool_calls]
            all_calls.extend(tool_calls)
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
            results = await asyncio.gather(
                *[
                    self._execute_tool_call(call, request.context, iteration)
                    for call in tool_calls
                ]
            )
            all_results.extend(results)
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
        )

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
        return LLMToolResult(
            tool_call_id=call.id,
            name=call.name,
            content=content,
            is_error=not ok,
            error=(
                envelope_payload.get("error", {}).get("message")
                if isinstance(envelope_payload.get("error"), dict)
                else None
            ),
        )

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

    @staticmethod
    def _extract_next_cursor(payload: dict[str, Any]) -> Any | None:
        data = payload.get("data")
        if isinstance(data, dict):
            return data.get("next_cursor") or data.get("cursor")
        return None

    @staticmethod
    def _stringify_tool_result(result: LLMToolResult) -> str:
        if isinstance(result.content, str):
            return result.content
        return json.dumps(result.content, ensure_ascii=True, default=str)

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
        if isinstance(allowed, list) and allowed and call.name not in set(map(str, allowed)):
            return f"Tool '{call.name}' is not allowed by policy constraints."
        return None
