from __future__ import annotations

from server.common.typing import is_json_array, is_json_object, json_object

import asyncio
import copy
import logging
import re
import time
from datetime import datetime
from collections.abc import Callable
from typing import Any

from server.domain.agent.execution import AgentExecutionContext
from server.domain.agent.pipeline import (
    PlannedToolResult,
    ToolPlan,
    ToolPlanStep,
    ToolResultProvenance,
)
from server.domain.agent.runtime import canonical_call_fingerprint
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
        fingerprints: set[str] = set()
        while remaining:
            ready = [
                step
                for step in remaining.values()
                if all(
                    dependency in completed and completed[dependency].ok
                    for dependency in step.depends_on
                )
            ]
            blocked = [
                step
                for step in remaining.values()
                if any(
                    dependency in completed and not completed[dependency].ok
                    for dependency in step.depends_on
                )
            ]
            for step in blocked:
                result = self._dependency_error(step, code="dependency_failed")
                completed[step.step_id] = result
                remaining.pop(step.step_id, None)
                if on_tool_completed is not None:
                    on_tool_completed(result)
            if not ready:
                if not remaining:
                    break
                unresolved = list(remaining.values())
                remaining.clear()
                for step in unresolved:
                    completed[step.step_id] = self._dependency_error(step)
                    if on_tool_completed is not None:
                        on_tool_completed(completed[step.step_id])
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
                            completed=completed,
                            fingerprints=fingerprints,
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
        completed: dict[str, PlannedToolResult],
        fingerprints: set[str],
        on_tool_started: Callable[[ToolPlanStep], None] | None = None,
        on_tool_completed: Callable[[PlannedToolResult], None] | None = None,
    ) -> PlannedToolResult:
        arguments, binding_error = self._resolve_input_bindings(step, completed)
        effective_step = step.model_copy(update={"arguments": arguments})
        if on_tool_started is not None:
            on_tool_started(effective_step)
        if binding_error is not None:
            result = PlannedToolResult(
                step_id=step.step_id,
                ok=False,
                error_code="invalid_input_binding",
                error_message=binding_error,
                provenance=ToolResultProvenance(
                    tool_name=step.tool_name,
                    capability_id=step.capability_id,
                ),
            )
            if on_tool_completed is not None:
                on_tool_completed(result)
            return result
        retryable = set(step.retry_policy.retryable_error_codes)
        fingerprint = canonical_call_fingerprint(step.tool_name, arguments)
        if fingerprint in fingerprints:
            result = PlannedToolResult(
                step_id=step.step_id,
                ok=False,
                error_code="duplicate_tool_call",
                error_message="The same validated tool call was already completed in this run.",
                provenance=ToolResultProvenance(
                    tool_name=step.tool_name,
                    capability_id=step.capability_id,
                    call_fingerprint=fingerprint,
                ),
            )
            if on_tool_completed is not None:
                on_tool_completed(result)
            return result
        fingerprints.add(fingerprint)
        for attempt in range(1, step.retry_policy.max_attempts + 1):
            started = time.perf_counter()
            try:
                envelope = await asyncio.wait_for(
                    self.tool_registry.execute_native_tool(
                        step.tool_name,
                        arguments,
                        context,
                    ),
                    timeout=step.timeout_seconds,
                )
                payload = envelope.to_dict()
            except TimeoutError:
                payload = {
                    "ok": False,
                    "data": None,
                    "error": {
                        "code": "tool_timeout",
                        "message": "Tool execution timed out.",
                    },
                }
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            error = json_object(payload.get("error"))
            error_code = str(error.get("code") or "") or None
            ok = bool(payload.get("ok"))
            data = payload.get("data")
            validation_error = self._validate_result(step, data) if ok else None
            if ok and validation_error is None:
                result = PlannedToolResult(
                    step_id=step.step_id,
                    ok=True,
                    data=data if is_json_object(data) else {"value": data},
                    provenance=ToolResultProvenance(
                        tool_name=step.tool_name,
                        capability_id=step.capability_id,
                        attempt=attempt,
                        elapsed_ms=elapsed_ms,
                        call_fingerprint=fingerprint,
                        **self._provenance_fields(data),
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
                        call_fingerprint=fingerprint,
                        **self._provenance_fields(data),
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
                        call_fingerprint=fingerprint,
                        **self._provenance_fields(data),
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
            await asyncio.sleep(0.25)
        raise AssertionError("unreachable")

    # -------------------------------------------------------------------------
    @staticmethod
    def _validate_result(step: ToolPlanStep, data: Any) -> str | None:
        if not is_json_object(data):
            return "Tool output must be an object."
        if step.tool_name == "execute_geospatial_capability":
            if data.get("ok") is False:
                error = data.get("error")
                if is_json_object(error):
                    return str(error.get("message") or "Capability execution failed.")
                return "Capability execution failed."
            if data.get("capability_id") != step.capability_id:
                return "Tool output capability does not match the planned capability."
        status = ToolPlanExecutor._result_field(data, "result_status")
        if status in {"unavailable", "invalid", "error", "failed"}:
            return f"Tool output reported an unusable result status: {status}."
        return None

    # -------------------------------------------------------------------------
    @classmethod
    def _resolve_input_bindings(
        cls,
        step: ToolPlanStep,
        completed: dict[str, PlannedToolResult],
    ) -> tuple[dict[str, Any], str | None]:
        arguments = copy.deepcopy(step.arguments)
        for binding in step.input_bindings:
            source = completed.get(binding.source_step_id)
            if source is None or not source.ok:
                if binding.required:
                    return arguments, (
                        f"Required input source '{binding.source_step_id}' is unavailable."
                    )
                continue
            value = cls._lookup_path(
                source.model_dump(mode="json"), binding.source_path
            )
            if value is None and binding.required:
                return arguments, (
                    f"Required input '{binding.source_path}' was not produced by "
                    f"'{binding.source_step_id}'."
                )
            if value is not None:
                cls._set_path(arguments, binding.target, copy.deepcopy(value))
        return arguments, None

    # -------------------------------------------------------------------------
    @staticmethod
    def _path_parts(path: str) -> list[str]:
        return [
            part
            for part in re.findall(r"[^.\[\]]+", path.strip().lstrip("$."))
            if part
        ]

    # -------------------------------------------------------------------------
    @classmethod
    def _lookup_path(cls, value: Any, path: str) -> Any:
        current = value
        for part in cls._path_parts(path):
            if isinstance(current, dict):
                if part not in current:
                    return None
                current = current[part]
            elif isinstance(current, list) and part.isdigit():
                index = int(part)
                if index >= len(current):
                    return None
                current = current[index]
            else:
                return None
        return current

    # -------------------------------------------------------------------------
    @classmethod
    def _set_path(cls, target: dict[str, Any], path: str, value: Any) -> None:
        parts = cls._path_parts(path)
        if not parts:
            return
        current: Any = target
        for part in parts[:-1]:
            if not isinstance(current, dict):
                return
            nested = current.get(part)
            if not isinstance(nested, dict):
                nested = {}
                current[part] = nested
            current = nested
        if isinstance(current, dict):
            current[parts[-1]] = value

    # -------------------------------------------------------------------------
    @classmethod
    def _provenance_fields(cls, data: Any) -> dict[str, Any]:
        candidates: list[dict[str, Any]] = []
        if is_json_object(data):
            candidates.append(data)
            for key in (
                "result",
                "direct_result",
                "map_session",
                "metadata",
                "provenance",
            ):
                nested = data.get(key)
                if is_json_object(nested):
                    candidates.append(nested)
                    nested_result = nested.get("result")
                    if is_json_object(nested_result):
                        candidates.append(nested_result)
        provider = cls._first_string(
            candidates, "provider", "provider_id", "providerId"
        )
        observation_time = cls._first_string(
            candidates,
            "observation_time",
            "observationTime",
            "timestamp",
            "time",
        )
        source_url = cls._first_string(
            candidates, "source_url", "sourceUrl", "endpoint"
        )
        fetched_at = cls._first_datetime(
            candidates, "fetched_at", "fetchedAt", "retrieved_at"
        )
        coverage = cls._first_object(candidates, "coverage", "geographic_coverage")
        spatial_resolution = cls._first_string(
            candidates, "spatial_resolution", "spatialResolution", "resolution"
        )
        units_value = cls._first_object(candidates, "units", "unit_map") or {}
        units = {
            str(key): str(value)
            for key, value in units_value.items()
            if isinstance(key, str) and isinstance(value, str)
        }
        result_status = (
            cls._first_string(candidates, "result_status", "resultStatus")
            or "unknown"
        )
        result_type = (
            cls._first_string(candidates, "result_type", "resultType")
            or "unknown"
        )
        warnings = cls._first_string_list(candidates, "warnings")
        partial = any(bool(candidate.get("partial")) for candidate in candidates)
        return {
            "provider": provider,
            "fetched_at": fetched_at or datetime.now().astimezone(),
            "observation_time": observation_time,
            "coverage": coverage,
            "spatial_resolution": spatial_resolution,
            "units": units,
            "source_url": source_url,
            "result_status": result_status,
            "result_type": result_type,
            "partial": partial,
            "warnings": warnings,
        }

    # -------------------------------------------------------------------------
    @staticmethod
    def _result_field(value: Any, key: str) -> str | None:
        if not is_json_object(value):
            return None
        raw = value.get(key)
        return str(raw).strip().casefold() if isinstance(raw, str) else None

    # -------------------------------------------------------------------------
    @staticmethod
    def _first_string(
        candidates: list[dict[str, Any]], *keys: str
    ) -> str | None:
        for candidate in candidates:
            for key in keys:
                value = candidate.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return None

    # -------------------------------------------------------------------------
    @classmethod
    def _first_datetime(
        cls, candidates: list[dict[str, Any]], *keys: str
    ) -> datetime | None:
        value = cls._first_string(candidates, *keys)
        if value is None:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None

    # -------------------------------------------------------------------------
    @staticmethod
    def _first_object(
        candidates: list[dict[str, Any]], *keys: str
    ) -> dict[str, Any] | None:
        for candidate in candidates:
            for key in keys:
                value = candidate.get(key)
                if is_json_object(value):
                    return dict(value)
        return None

    # -------------------------------------------------------------------------
    @staticmethod
    def _first_string_list(
        candidates: list[dict[str, Any]], key: str
    ) -> list[str]:
        for candidate in candidates:
            value = candidate.get(key)
            if is_json_array(value):
                return [str(item) for item in value if isinstance(item, str)]
        return []

    # -------------------------------------------------------------------------
    @staticmethod
    def _dependency_error(
        step: ToolPlanStep,
        *,
        code: str = "dependency_cycle",
    ) -> PlannedToolResult:
        return PlannedToolResult(
            step_id=step.step_id,
            ok=False,
            error_code=code,
            error_message=(
                "A required predecessor failed."
                if code == "dependency_failed"
                else "Tool plan dependencies could not be resolved."
            ),
            provenance=ToolResultProvenance(
                tool_name=step.tool_name,
                capability_id=step.capability_id,
            ),
        )
