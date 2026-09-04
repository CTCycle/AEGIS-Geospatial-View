"""Bounded execution and safe operational telemetry for agent runs."""

from __future__ import annotations

import asyncio
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Generator


DEFAULT_RUN_SECONDS = 45.0
DEFAULT_STAGE_LIMITS: dict[str, float] = {
    "context_assembly": 2.0,
    "structured_intent_extraction": 20.0,
    "location_resolution": 12.0,
    "planning": 2.0,
    "tool_execution": 20.0,
    "map_assembly": 8.0,
    "response_synthesis": 8.0,
    "persistence": 3.0,
}


def _new_stage_metadata() -> dict[str, Any]:
    return {}


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


def _new_stage_observations() -> list[StageObservation]:
    return []


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

    def __post_init__(self) -> None:
        if self.total_seconds <= 0:
            raise ValueError("total_seconds must be positive")
        self.deadline_monotonic = self.started_monotonic + self.total_seconds

    deadline_monotonic: float = field(init=False)

    def remaining_seconds(self) -> float:
        return max(0.0, self.deadline_monotonic - time.monotonic())

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

    def ensure_available(self, stage: str) -> None:
        if self.remaining_seconds() <= 0.0:
            self.terminal_reason = "run_deadline_exhausted"
            raise TimeoutError(f"The agent run deadline expired before {stage}.")

    def record_model_call(self) -> None:
        self.model_calls += 1

    def record_tool_call(self) -> None:
        self.tool_calls += 1

    def record_retry(self) -> None:
        self.retry_count += 1

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
            error_code = str(getattr(exc, "code", "")) or type(exc).__name__
            raise
        finally:
            self.observations.append(
                StageObservation(
                    stage=stage,
                    status=status,
                    duration_ms=max(0, int((time.perf_counter() - started) * 1000)),
                    deadline_remaining_ms=max(
                        0, int(self.remaining_seconds() * 1000)
                    ),
                    error_code=error_code,
                    timeout_origin=timeout_origin,
                    metadata=dict(metadata or {}),
                )
            )

    def snapshot(self) -> dict[str, Any]:
        return {
            "total_budget_ms": int(self.total_seconds * 1000),
            "remaining_ms": max(0, int(self.remaining_seconds() * 1000)),
            "model_calls": self.model_calls,
            "tool_calls": self.tool_calls,
            "retry_count": self.retry_count,
            "terminal_reason": self.terminal_reason,
            "stages": [item.to_dict() for item in self.observations[-32:]],
        }
