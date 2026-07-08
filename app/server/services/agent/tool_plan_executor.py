from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any

from server.domain.agent.execution import AgentExecutionContext
from server.domain.agent.pipeline import (
    PlannedToolResult,
    ToolPlan,
    ToolPlanStep,
    ToolResultProvenance,
)
from server.services.agent.tool_registry import ToolRegistry

LOGGER = logging.getLogger(__name__)

###############################################################################
class ToolPlanExecutor:

    # -------------------------------------------------------------------------
    def __init__(self, *, tool_registry: ToolRegistry) -> None:
        self.tool_registry = tool_registry

    # -------------------------------------------------------------------------
    async def execute(
        self,
        plan: ToolPlan,
        context: AgentExecutionContext,
        *,
        on_tool_started: Callable[[ToolPlanStep], None] | None = None,
        on_tool_completed: Callable[[PlannedToolResult], None] | None = None,
    ) -> list[PlannedToolResult]:
        remaining = {step.step_id: step for step in plan.steps}
        completed: dict[str, PlannedToolResult] = {}
        while remaining:
            ready = [
                step
                for step in remaining.values()
                if all(dependency in completed for dependency in step.depends_on)
            ]
            if not ready:
                for step in remaining.values():
                    completed[step.step_id] = self._dependency_error(step)
                break
            grouped: dict[str, list[ToolPlanStep]] = {}
            for step in ready:
                group = step.parallel_group or f"serial:{step.step_id}"
                grouped.setdefault(group, []).append(step)
            for group, steps in grouped.items():
                LOGGER.info(
                    "tool_plan_group_started group=%s steps=%s",
                    group,
                    [step.step_id for step in steps],
                )
                results = await asyncio.gather(
                    *[
                        self._execute_step(
                            step,
                            context,
                            on_tool_started=on_tool_started,
                            on_tool_completed=on_tool_completed,
                        )
                        for step in steps
                    ]
                )
                for result in results:
                    completed[result.step_id] = result
                    remaining.pop(result.step_id, None)
        return [completed[step.step_id] for step in plan.steps]

    # -------------------------------------------------------------------------
    async def _execute_step(
        self,
        step: ToolPlanStep,
        context: AgentExecutionContext,
        *,
        on_tool_started: Callable[[ToolPlanStep], None] | None = None,
        on_tool_completed: Callable[[PlannedToolResult], None] | None = None,
    ) -> PlannedToolResult:
        if on_tool_started is not None:
            on_tool_started(step)
        retryable = set(step.retry_policy.retryable_error_codes)
        for attempt in range(1, step.retry_policy.max_attempts + 1):
            started = time.perf_counter()
            try:
                envelope = await asyncio.wait_for(
                    self.tool_registry.execute_native_tool(
                        step.tool_name,
                        step.arguments,
                        context,
                    ),
                    timeout=step.timeout_seconds,
                )
                payload = envelope.to_dict()
            except TimeoutError:
                payload = {
                    "ok": False,
                    "data": None,
                    "error": {"code": "tool_timeout", "message": "Tool execution timed out."},
                }
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            error = payload.get("error") if isinstance(payload.get("error"), dict) else {}
            error_code = str(error.get("code") or "") or None
            ok = bool(payload.get("ok"))
            data = payload.get("data")
            validation_error = self._validate_result(step, data) if ok else None
            if ok and validation_error is None:
                result = PlannedToolResult(
                    step_id=step.step_id,
                    ok=True,
                    data=data if isinstance(data, dict) else {"value": data},
                    provenance=ToolResultProvenance(
                        tool_name=step.tool_name,
                        capability_id=step.capability_id,
                        attempt=attempt,
                        elapsed_ms=elapsed_ms,
                    ),
                )
                if on_tool_completed is not None:
                    on_tool_completed(result)
                return result
            if validation_error is not None:
                result = PlannedToolResult(
                    step_id=step.step_id,
                    ok=False,
                    validation_error=validation_error,
                    error_code="invalid_tool_output",
                    error_message=validation_error,
                    provenance=ToolResultProvenance(
                        tool_name=step.tool_name,
                        capability_id=step.capability_id,
                        attempt=attempt,
                        elapsed_ms=elapsed_ms,
                    ),
                )
                if on_tool_completed is not None:
                    on_tool_completed(result)
                return result
            if error_code not in retryable or attempt >= step.retry_policy.max_attempts:
                result = PlannedToolResult(
                    step_id=step.step_id,
                    ok=False,
                    error_code=error_code or "tool_execution_error",
                    error_message=str(error.get("message") or "Tool execution failed."),
                    provenance=ToolResultProvenance(
                        tool_name=step.tool_name,
                        capability_id=step.capability_id,
                        attempt=attempt,
                        elapsed_ms=elapsed_ms,
                    ),
                )
                if on_tool_completed is not None:
                    on_tool_completed(result)
                return result
            LOGGER.warning(
                "tool_plan_step_retry step=%s tool=%s attempt=%s code=%s",
                step.step_id,
                step.tool_name,
                attempt,
                error_code,
            )
        raise AssertionError("unreachable")

    # -------------------------------------------------------------------------
    @staticmethod
    def _validate_result(step: ToolPlanStep, data: Any) -> str | None:
        if not isinstance(data, dict):
            return "Tool output must be an object."
        if step.tool_name == "execute_geospatial_capability":
            if data.get("ok") is False:
                error = data.get("error")
                if isinstance(error, dict):
                    return str(error.get("message") or "Capability execution failed.")
                return "Capability execution failed."
            if data.get("capability_id") != step.capability_id:
                return "Tool output capability does not match the planned capability."
        return None

    # -------------------------------------------------------------------------
    @staticmethod
    def _dependency_error(step: ToolPlanStep) -> PlannedToolResult:
        return PlannedToolResult(
            step_id=step.step_id,
            ok=False,
            error_code="dependency_cycle",
            error_message="Tool plan dependencies could not be resolved.",
            provenance=ToolResultProvenance(
                tool_name=step.tool_name,
                capability_id=step.capability_id,
            ),
        )
