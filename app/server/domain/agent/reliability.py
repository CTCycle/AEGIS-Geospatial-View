"""Bounded execution and safe operational telemetry for agent runs."""

from __future__ import annotations

import asyncio
import time
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from typing import Any, Generator


DEFAULT_RUN_SECONDS = 75.0
DEFAULT_STAGE_LIMITS: dict[str, float] = {
    "context_assembly": 2.0,
    "structured_intent_extraction": 30.0,
    "location_resolution": 12.0,
    "planning": 2.0,
    "tool_execution": 20.0,
    "map_assembly": 8.0,
    "response_synthesis": 8.0,
    "persistence": 3.0,
}


###############################################################################
def _new_stage_metadata() -> dict[str, Any]:
    return {}


###############################################################################
@dataclass(frozen=True)
class StageObservation:
    """A bounded stage record; it never contains prompts or provider bodies."""

    stage: str
    status: str
    duration_ms: int
    deadline_remaining_ms: int | None = None
    error_code: str | None = None
    timeout_origin: str | None = None
    metadata: dict[str, Any] = field(default_factory=_new_stage_metadata)

    # -------------------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "deadline_remaining_ms": self.deadline_remaining_ms,
            "error_code": self.error_code,
            "timeout_origin": self.timeout_origin,
            "metadata": dict(self.metadata),
        }


###############################################################################
def _new_stage_observations() -> list[StageObservation]:
    return []


def _new_pipeline_reach() -> dict[str, str]:
    return {
        "context_assembly": "not_reached",
        "structured_intent_extraction": "not_reached",
        "policy": "not_reached",
        "location_resolution": "not_reached",
        "planning": "not_reached",
        "tool_execution": "not_reached",
        "map_assembly": "not_reached",
        "render_ack": "not_reached",
        "response_synthesis": "not_reached",
        "persistence": "not_reached",
    }


###############################################################################
@dataclass
class AgentExecutionBudget:
    """One absolute deadline and bounded counters for a complete run."""

    total_seconds: float = DEFAULT_RUN_SECONDS
    stage_limits: dict[str, float] = field(
        default_factory=lambda: dict(DEFAULT_STAGE_LIMITS)
    )
    started_monotonic: float = field(default_factory=time.monotonic)
    observations: list[StageObservation] = field(
        default_factory=_new_stage_observations
    )
    model_calls: int = 0
    tool_calls: int = 0
    retry_count: int = 0
    terminal_reason: str | None = None
    terminal_stage: str | None = None
    parser_contract: dict[str, Any] | None = None
    pipeline_reach: dict[str, str] = field(default_factory=_new_pipeline_reach)

    # -------------------------------------------------------------------------
    def __post_init__(self) -> None:
        if self.total_seconds <= 0:
            raise ValueError("total_seconds must be positive")
        self.deadline_monotonic = self.started_monotonic + self.total_seconds

    deadline_monotonic: float = field(init=False)

    # -------------------------------------------------------------------------
    def remaining_seconds(self) -> float:
        return max(0.0, self.deadline_monotonic - time.monotonic())

    # -------------------------------------------------------------------------
    def stage_deadline(
        self, stage: str, *, requested_seconds: float | None = None
    ) -> float:
        limit = self.stage_limits.get(stage)
        if requested_seconds is not None:
            limit = requested_seconds if limit is None else min(limit, requested_seconds)
        remaining = self.remaining_seconds()
        if limit is None:
            return time.monotonic() + remaining
        return time.monotonic() + min(max(0.0, limit), remaining)

    # -------------------------------------------------------------------------
    def ensure_available(self, stage: str) -> None:
        if self.remaining_seconds() <= 0.0:
            self.terminal_reason = "run_deadline_exhausted"
            raise TimeoutError(f"The agent run deadline expired before {stage}.")

    # -------------------------------------------------------------------------
    def record_model_call(self) -> None:
        self.model_calls += 1

    # -------------------------------------------------------------------------
    def record_tool_call(self) -> None:
        self.tool_calls += 1

    # -------------------------------------------------------------------------
    def record_retry(self) -> None:
        self.retry_count += 1

    # -------------------------------------------------------------------------
    def mark_stage_failed(
        self,
        stage: str,
        *,
        error_code: str | None = None,
        timeout_origin: str | None = None,
    ) -> None:
        """Correct a returned failure that did not raise through ``observe``.

        Parser services intentionally return a non-executable failure contract
        so the response layer can provide a bounded diagnostic.  The stage
        record still needs to reflect that extraction failed rather than
        looking like a successful parse followed by policy clarification.
        """
        for index in range(len(self.observations) - 1, -1, -1):
            observation = self.observations[index]
            if observation.stage != stage:
                continue
            self.observations[index] = replace(
                observation,
                status="failed",
                error_code=error_code or observation.error_code,
                timeout_origin=timeout_origin or observation.timeout_origin,
            )
            break
        self.pipeline_reach[stage] = "failed"
        self.terminal_stage = self.terminal_stage or stage

    # -------------------------------------------------------------------------
    @contextmanager
    def observe(
        self,
        stage: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> Generator[None, None, None]:
        started = time.perf_counter()
        status = "success"
        error_code: str | None = None
        timeout_origin: str | None = None
        try:
            self.ensure_available(stage)
            yield
        except asyncio.CancelledError:
            status = "cancelled"
            error_code = "cancelled"
            timeout_origin = "cancelled"
            self.terminal_reason = self.terminal_reason or "cancelled"
            raise
        except TimeoutError as exc:
            status = "timeout"
            timeout_origin = str(getattr(exc, "timeout_origin", "") or "") or (
                "application_deadline"
                if self.remaining_seconds() <= 0.0
                else "provider_transport"
            )
            error_code = str(getattr(exc, "code", "") or "timeout")
            self.terminal_reason = self.terminal_reason or (
                "application_deadline"
                if timeout_origin == "application_deadline"
                else "provider_timeout"
            )
            raise
        except Exception as exc:
            timeout_origin_value = getattr(exc, "timeout_origin", None)
            if timeout_origin_value:
                status = "timeout"
                timeout_origin = str(timeout_origin_value)
            else:
                status = "failed"
            error_code = str(getattr(exc, "code", "")) or type(exc).__name__
            raise
        finally:
            observation = StageObservation(
                stage=stage,
                status=status,
                duration_ms=max(0, int((time.perf_counter() - started) * 1000)),
                deadline_remaining_ms=max(0, int(self.remaining_seconds() * 1000)),
                error_code=error_code,
                timeout_origin=timeout_origin,
                metadata=dict(metadata or {}),
            )
            self.observations.append(observation)
            self.pipeline_reach[stage] = status
            if status in {"failed", "timeout", "cancelled"}:
                self.terminal_stage = self.terminal_stage or stage

    # -------------------------------------------------------------------------
    def snapshot(self) -> dict[str, Any]:
        return {
            "total_budget_ms": int(self.total_seconds * 1000),
            "remaining_ms": max(0, int(self.remaining_seconds() * 1000)),
            "model_calls": self.model_calls,
            "tool_calls": self.tool_calls,
            "retry_count": self.retry_count,
            "terminal_reason": self.terminal_reason,
            "terminal_stage": self.terminal_stage,
            "parser_contract": (
                dict(self.parser_contract) if self.parser_contract is not None else None
            ),
            "pipeline_reach": dict(self.pipeline_reach),
            "stages": [item.to_dict() for item in self.observations[-32:]],
        }
