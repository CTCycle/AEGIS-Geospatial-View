"""Single validation and execution boundary for native-v2 tools."""

from __future__ import annotations

import asyncio
import time
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ValidationError

from server.domain.agent.capability_domains import CapabilityDomain
from server.domain.agent.capability_route import AgentState
from server.domain.agent.tool_result import (
    ToolExecutionError,
    ToolExecutionMetadata,
    ToolResult,
    ValidationIssue,
)
from server.domain.agent.tools import RegisteredTool
from server.domain.llm.types import LLMToolCall
from server.services.agent.tool_registry import ToolRegistry


###############################################################################
class ToolExecutor:
    def __init__(
        self,
        *,
        tool_registry: ToolRegistry,
        policy_engine: Any | None = None,
        timeout_seconds: float = 45.0,
    ) -> None:
        self.tool_registry = tool_registry
        self.policy_engine = policy_engine
        self.timeout_seconds = max(0.01, float(timeout_seconds))

    # -------------------------------------------------------------------------
    async def execute_tool(
        self,
        tool_call: LLMToolCall,
        state: AgentState,
        budget: Any,
    ) -> ToolResult:
        started = time.perf_counter()
        call_id = tool_call.id or f"call_{uuid4().hex}"
        if tool_call.parse_error is not None or tool_call.arguments is None:
            return self._failure(
                call_id=call_id,
                tool_name=tool_call.name,
                started=started,
                error=ToolExecutionError(
                    error_type="malformed_call",
                    code=tool_call.parse_error or "arguments_missing",
                    message="The model returned malformed tool-call arguments.",
                    retryable=False,
                    recovery="correct_arguments",
                ),
            )

        registered = self.tool_registry.get(tool_call.name)
        if registered is None:
            return self._failure(
                call_id=call_id,
                tool_name=tool_call.name,
                started=started,
                error=ToolExecutionError(
                    error_type="unknown_tool",
                    code="unknown_tool",
                    message=f"No tool named '{tool_call.name}' is exposed.",
                    retryable=False,
                    recovery="choose_alternate_tool",
                ),
            )

        try:
            arguments = registered.input_model.model_validate(tool_call.arguments)
        except ValidationError as exc:
            issues = [
                ValidationIssue(
                    path=".".join(str(part) for part in error.get("loc", ())) or "$",
                    code=str(error.get("type") or "invalid"),
                    message=str(error.get("msg") or "Invalid tool argument."),
                )
                for error in exc.errors()
            ]
            return self._failure(
                call_id=call_id,
                tool_name=tool_call.name,
                started=started,
                error=ToolExecutionError(
                    error_type="schema_validation",
                    code="invalid_arguments",
                    message="Tool arguments failed schema validation.",
                    retryable=False,
                    recovery="correct_arguments",
                    validation_errors=issues,
                ),
            )

        if registered.semantic_validator is not None:
            semantic_errors = registered.semantic_validator(arguments, state)
            if semantic_errors:
                return self._failure(
                    call_id=call_id,
                    tool_name=tool_call.name,
                    started=started,
                    error=ToolExecutionError(
                        error_type="semantic_validation",
                        code="semantic_validation_failed",
                        message="Tool arguments failed semantic validation.",
                        retryable=False,
                        recovery="correct_arguments",
                        validation_errors=[
                            ValidationIssue(
                                path="$",
                                code="semantic_validation_failed",
                                message=str(message),
                            )
                            for message in semantic_errors[:8]
                        ],
                    ),
                )

        authorization = self._authorize(registered, arguments, state)
        if not authorization[0]:
            return self._failure(
                call_id=call_id,
                tool_name=tool_call.name,
                started=started,
                error=ToolExecutionError(
                    error_type="policy_rejection",
                    code="policy_rejection",
                    message=authorization[1] or "Tool call was rejected by policy.",
                    retryable=False,
                    recovery="choose_alternate_tool",
                ),
            )

        try:
            budget.ensure_available("tool_execution")
            remaining = float(budget.remaining_seconds())
            timeout = min(self.timeout_seconds, max(0.01, remaining))
            raw_result = await asyncio.wait_for(
                registered.handler(arguments, state), timeout=timeout
            )
        except asyncio.TimeoutError:
            return self._failure(
                call_id=call_id,
                tool_name=tool_call.name,
                started=started,
                error=ToolExecutionError(
                    error_type="timeout",
                    code="tool_timeout",
                    message=f"Tool '{tool_call.name}' timed out.",
                    retryable=False,
                    recovery="replan",
                    timeout_origin="tool_executor",
                ),
            )
        except Exception:
            # Provider-specific failures are normalized by the capability
            # handler.  The outer boundary never exposes exception details.
            return self._failure(
                call_id=call_id,
                tool_name=tool_call.name,
                started=started,
                error=ToolExecutionError(
                    error_type="internal_error",
                    code="tool_execution_error",
                    message=f"Tool '{tool_call.name}' failed during execution.",
                    retryable=False,
                    recovery="terminal",
                ),
            )

        try:
            result = registered.result_normalizer(raw_result, call_id)
        except Exception:
            return self._failure(
                call_id=call_id,
                tool_name=tool_call.name,
                started=started,
                error=ToolExecutionError(
                    error_type="invalid_tool_output",
                    code="invalid_tool_output",
                    message=f"Tool '{tool_call.name}' returned an invalid result.",
                    retryable=False,
                    recovery="terminal",
                ),
            )
        state.tool_calls += 1
        state.tool_results.append(result)
        return result

    # -------------------------------------------------------------------------
    def _authorize(
        self,
        tool: RegisteredTool,
        arguments: BaseModel,
        state: AgentState,
    ) -> tuple[bool, str | None]:
        authorize = getattr(self.policy_engine, "authorize", None)
        if callable(authorize):
            result = authorize(tool, arguments, state)
            allowed = bool(getattr(result, "allowed", False))
            return allowed, getattr(result, "reason", None)
        if state.route is not None:
            route_domains = {
                state.route.primary_domain,
                *state.route.secondary_domains,
            }
            if (
                CapabilityDomain.MIXED not in route_domains
                and tool.domains
                and not tool.domains.intersection(route_domains)
            ):
                return False, "Tool is outside the validated capability route."
        capability_id = getattr(arguments, "capability_id", None)
        if capability_id and state.capability_ids and capability_id not in state.capability_ids:
            return False, "Capability is outside the validated shortlist."
        return True, None

    # -------------------------------------------------------------------------
    @staticmethod
    def _failure(
        *,
        call_id: str,
        tool_name: str,
        started: float,
        error: ToolExecutionError,
    ) -> ToolResult:
        duration_ms = max(0, int((time.perf_counter() - started) * 1000))
        return ToolResult(
            call_id=call_id,
            tool_name=tool_name,
            status="failed",
            summary=error.message,
            error=error,
            metadata=ToolExecutionMetadata(duration_ms=duration_ms),
        )
