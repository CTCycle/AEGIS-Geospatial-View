"""Single validation and execution boundary for native agent tools."""

from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Awaitable, Callable
from typing import Any, cast
from uuid import uuid4

from pydantic import BaseModel, ValidationError

from server.domain.agent.capability_domains import CapabilityDomain
from server.domain.agent.capability_route import AgentRunState
from server.domain.agent.reliability import (
    AgentExecutionBudget,
    ExecutionBudgetExceeded,
)
from server.domain.agent.trace import AgentTraceEvent, redact_trace_value
from server.domain.agent.tool_result import (
    ToolExecutionError,
    ToolExecutionMetadata,
    ModelObservation,
    ToolResult,
    ValidationIssue,
)
from server.domain.agent.tools import RegisteredTool
from server.domain.llm.types import LLMToolCall
from server.services.agent.tool_registry import ToolRegistry

###############################################################################
class ToolExecutor:

    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        tool_registry: ToolRegistry,
        policy_engine: Any | None = None,
        timeout_seconds: float = 45.0,
        trace_callback: Callable[
            [AgentTraceEvent], Awaitable[None] | None
        ] | None = None,
    ) -> None:
        self.tool_registry = tool_registry
        self.policy_engine = policy_engine
        self.timeout_seconds = max(0.01, float(timeout_seconds))
        self.trace_callback = trace_callback

    # -------------------------------------------------------------------------
    async def execute_tool(
        self,
        tool_call: LLMToolCall,
        state: AgentRunState,
        budget: AgentExecutionBudget,
        *,
        trace_callback: Callable[
            [AgentTraceEvent], Awaitable[None] | None
        ] | None = None,
        iteration: int | None = None,
        task_id: str | None = None,
    ) -> ToolResult:
        call_id = tool_call.id or f"call_{uuid4().hex}"
        await self._emit_tool_selected(
            state,
            tool_call,
            call_id=call_id,
            iteration=iteration,
            task_id=task_id,
            callback=trace_callback or self.trace_callback,
        )
        result = await self._execute_tool(
            tool_call,
            state,
            budget,
            call_id=call_id,
        )
        if not any(item.call_id == result.call_id for item in state.tool_results):
            # The executor is the only application boundary that may publish a
            # normalized result.  The loop can still merge it idempotently when
            # it applies the observation to its state.
            state.tool_results.append(result)
        state.tool_trace.append(
            self._result_trace_payload(
                result,
                iteration=iteration,
                task_id=task_id,
            )
        )
        await self._emit_tool_result(
            state,
            result,
            iteration=iteration,
            task_id=task_id,
            callback=trace_callback or self.trace_callback,
        )
        return result

    # -------------------------------------------------------------------------
    async def _emit_tool_selected(
        self,
        state: AgentRunState,
        tool_call: LLMToolCall,
        *,
        call_id: str,
        iteration: int | None,
        task_id: str | None,
        callback: Callable[[AgentTraceEvent], Awaitable[None] | None] | None,
    ) -> None:
        arguments, redacted_fields = redact_trace_value(tool_call.arguments or {})
        redaction = {
            "policy": "trace-safe-v1",
            "applied": bool(redacted_fields),
            "fields": redacted_fields,
            "raw_payload_omitted": True,
        }
        payload = {
            "arguments": arguments,
            "parse_error": tool_call.parse_error,
            "redaction": redaction,
            "boundary": "tool_executor",
        }
        state.tool_trace.append(
            {
                "kind": "tool_selected",
                "call_id": call_id,
                "tool": tool_call.name,
                "tool_name": tool_call.name,
                "iteration": iteration,
                "task_id": task_id,
                "status": "selected",
                "arguments": arguments,
                "redaction": redaction,
                "boundary": "tool_executor",
            }
        )
        await self._emit_trace(
            state,
            AgentTraceEvent(
                kind="tool_selected",
                run_id=state.run_id or state.request_id,
                run_version=state.run_version,
                sequence=self._trace_sequence(state),
                iteration=iteration if iteration and iteration > 0 else None,
                task_id=task_id,
                call_id=call_id,
                tool_name=tool_call.name,
                redaction=redaction,
                payload=payload,
            ),
            callback,
        )

    # -------------------------------------------------------------------------
    async def _emit_tool_result(
        self,
        state: AgentRunState,
        result: ToolResult,
        *,
        iteration: int | None,
        task_id: str | None,
        callback: Callable[[AgentTraceEvent], Awaitable[None] | None] | None,
    ) -> None:
        payload = self._result_trace_payload(
            result,
            iteration=iteration,
            task_id=task_id,
        )
        redaction = dict(payload.get("redaction") or {})
        await self._emit_trace(
            state,
            AgentTraceEvent(
                kind="tool_result",
                run_id=state.run_id or state.request_id,
                run_version=state.run_version,
                sequence=self._trace_sequence(state),
                iteration=iteration if iteration and iteration > 0 else None,
                task_id=task_id,
                call_id=result.call_id,
                tool_name=result.tool_name,
                redaction=redaction,
                payload=payload,
            ),
            callback,
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def _result_trace_payload(
        result: ToolResult,
        *,
        iteration: int | None,
        task_id: str | None,
    ) -> dict[str, Any]:
        observation = ModelObservation.from_tool_result(result, max_chars=4096)
        projected, result_fields = redact_trace_value(
            observation.result,
            path="$.result",
        )
        metadata, metadata_fields = redact_trace_value(
            result.metadata.model_dump(mode="json", exclude_none=True),
            path="$.metadata",
        )
        error, error_fields = redact_trace_value(
            result.error.model_dump(mode="json", exclude_none=True)
            if result.error is not None
            else None,
            path="$.error",
        )
        fields = list(
            dict.fromkeys([*result_fields, *metadata_fields, *error_fields])
        )
        redaction = {
            "policy": "trace-safe-v1",
            "applied": bool(fields),
            "fields": fields,
            "raw_payload_omitted": True,
        }
        return {
            "kind": "tool_result",
            "call_id": result.call_id,
            "tool": result.tool_name,
            "tool_name": result.tool_name,
            "iteration": iteration,
            "task_id": task_id,
            "status": result.status,
            "summary": result.summary[:1000],
            "semantic_outcome": result.semantic_outcome,
            "result": projected,
            "evidence_refs": list(dict.fromkeys(result.evidence_refs))[:16],
            "map_candidate_id": result.map_candidate_id,
            "metadata": metadata,
            "error": error,
            "recovery": result.error.recovery if result.error else None,
            "redaction": redaction,
            "boundary": "tool_executor",
        }

    # -------------------------------------------------------------------------
    async def _emit_trace(
        self,
        state: AgentRunState,
        event: AgentTraceEvent,
        callback: Callable[[AgentTraceEvent], Awaitable[None] | None] | None,
    ) -> None:
        if callback is None:
            return
        emitted = callback(event)
        if inspect.isawaitable(emitted):
            await emitted

    # -------------------------------------------------------------------------
    @staticmethod
    def _trace_sequence(state: AgentRunState) -> int:
        return max(1, len(state.tool_trace))

    # -------------------------------------------------------------------------
    async def _execute_tool(
        self,
        tool_call: LLMToolCall,
        state: AgentRunState,
        budget: AgentExecutionBudget,
        *,
        call_id: str | None = None,
    ) -> ToolResult:
        started = time.perf_counter()
        call_id = call_id or tool_call.id or f"call_{uuid4().hex}"
        # Count every model-issued attempt, including malformed and rejected
        # calls.  The loop budget is an attempt budget, not only a successful
        # provider-execution budget.
        budget.ensure_available("tool_call")
        record_tool_call = getattr(budget, "record_tool_call", None)
        if callable(record_tool_call):
            record_tool_call()
        state.tool_calls += 1
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
                data={
                    "correction": self._correction_payload(
                        tool_call,
                        registered=None,
                    )
                },
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
                data={
                    "correction": self._correction_payload(
                        tool_call,
                        registered=registered,
                        validation_errors=issues,
                    )
                },
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
                    data={
                        "correction": self._correction_payload(
                            tool_call,
                            registered=registered,
                            validation_errors=[
                                ValidationIssue(
                                    path="$",
                                    code="semantic_validation_failed",
                                    message=str(message),
                                )
                                for message in semantic_errors[:8]
                            ],
                            canonical_arguments=arguments.model_dump(
                                mode="json", exclude_none=True
                            ),
                        )
                    },
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

        execution_stage = (
            "map_assembly"
            if tool_call.name == "apply_map_plan"
            else "tool_execution"
        )
        budget.ensure_available(execution_stage)
        timeout = budget.operation_timeout(
            execution_stage,
            requested_seconds=self.timeout_seconds,
        )
        try:
            with budget.observe(
                execution_stage,
                metadata={"tool": tool_call.name, "call_id": call_id},
            ):
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
        except ExecutionBudgetExceeded:
            raise
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
        return result

    # -------------------------------------------------------------------------
    def _authorize(
        self,
        tool: RegisteredTool,
        arguments: BaseModel,
        state: AgentRunState,
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
        data: dict[str, Any] | None = None,
    ) -> ToolResult:
        duration_ms = max(0, int((time.perf_counter() - started) * 1000))
        return ToolResult(
            call_id=call_id,
            tool_name=tool_name,
            status="failed",
            summary=error.message,
            data=data,
            error=error,
            metadata=ToolExecutionMetadata(duration_ms=duration_ms),
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def _correction_payload(
        tool_call: LLMToolCall,
        *,
        registered: RegisteredTool | None,
        validation_errors: list[ValidationIssue] | None = None,
        canonical_arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return a bounded, executable correction for invalid arguments.

        The error object remains the typed source of truth.  This companion
        payload gives the model one stable retry shape and the exact exposed
        schema without replaying arbitrary malformed arguments or provider
        payloads into the next request.
        """

        schema: dict[str, Any] = {}
        if registered is not None:
            raw_schema = registered.input_model.model_json_schema()
            schema = cast(
                dict[str, Any],
                _bounded_correction_value(raw_schema, depth=0),
            )
        raw_arguments = tool_call.arguments
        raw_properties: Any = schema.get("properties")
        properties: dict[str, Any] = (
            cast(dict[str, Any], raw_properties)
            if isinstance(raw_properties, dict)
            else {}
        )
        allowed: set[str] = set(properties)
        canonical: dict[str, Any]
        if canonical_arguments is not None:
            canonical = dict(canonical_arguments)
        elif isinstance(raw_arguments, dict):
            canonical = {
                str(key): value
                for key, value in raw_arguments.items()
                if not allowed or str(key) in allowed
            }
        else:
            canonical = {}
        raw_required: Any = schema.get("required")
        required: list[str] = (
            [str(item) for item in cast(list[Any], raw_required)[:32]]
            if isinstance(raw_required, list)
            else []
        )
        return {
            "tool_name": tool_call.name,
            "retry": "call the same tool with canonical_arguments only",
            "canonical_arguments": _bounded_correction_value(canonical, depth=0),
            "schema": schema,
            "required": required,
            "validation_errors": [
                issue.model_dump(mode="json")
                for issue in (validation_errors or [])[:8]
            ],
        }


###############################################################################
def _bounded_correction_value(value: Any, *, depth: int, max_depth: int = 4) -> Any:
    """Bound schemas and arguments before exposing them to a model retry."""

    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:500]
    if depth >= max_depth:
        return "[truncated]"
    if isinstance(value, dict):
        mapping: dict[str, Any] = cast(dict[str, Any], value)
        return {
            str(key): _bounded_correction_value(child, depth=depth + 1)
            for key, child in list(mapping.items())[:32]
        }
    if isinstance(value, list):
        items: list[Any] = cast(list[Any], value)
        return [
            _bounded_correction_value(child, depth=depth + 1)
            for child in items[:32]
        ]
    return str(value)[:500]
