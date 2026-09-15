"""Bounded execution and safe operational telemetry for agent runs."""

from __future__ import annotations

import asyncio
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Generator


INITIAL_RUN_SECONDS = 90.0
SIMPLE_RUN_SECONDS = 150.0
COMPLEX_RUN_SECONDS = 300.0
DEFAULT_RUN_SECONDS = INITIAL_RUN_SECONDS
DEFAULT_STAGE_LIMITS: dict[str, float] = {
    "context_assembly": 5.0,
    "route_request": 60.0,
    "model_step": 60.0,
    "tool_execution": 90.0,
    "map_assembly": 20.0,
    "render_ack": 90.0,
    "persistence": 5.0,
}

###############################################################################
class ExecutionBudgetExceeded(RuntimeError):
    """Raised when a bounded run cannot start another counted operation."""

    def __init__(self, reason: str, stage: str) -> None:
        self.reason = reason
        self.stage = stage
        super().__init__(f"The {stage} budget was exhausted.")


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


###############################################################################
@dataclass
class AgentExecutionBudget:
    """One absolute deadline and bounded counters for a complete run."""

    total_seconds: float = DEFAULT_RUN_SECONDS
    hard_max_seconds: float = COMPLEX_RUN_SECONDS
    simple_run_seconds: float = SIMPLE_RUN_SECONDS
    stage_limits: dict[str, float] = field(
        default_factory=lambda: dict(DEFAULT_STAGE_LIMITS)
    )
    started_monotonic: float = field(default_factory=time.monotonic)
    observations: list[StageObservation] = field(
        default_factory=_new_stage_observations
    )
    model_calls: int = 0
    tool_calls: int = 0
    state_transitions: int = 0
    max_model_calls: int | None = None
    max_tool_calls: int | None = None
    max_state_transitions: int | None = None
    retry_count: int = 0
    terminal_reason: str | None = None
    terminal_stage: str | None = None
    run_profile: str = "initial"
    context_allocations: list[dict[str, Any]] = field(
        default_factory=lambda: list[dict[str, Any]]()
    )
    iteration_traces: list[dict[str, Any]] = field(
        default_factory=lambda: list[dict[str, Any]]()
    )
    completion_requirements: list[str] = field(
        default_factory=lambda: list[str]()
    )
    stopping_reason: str | None = None

    # -------------------------------------------------------------------------
    def __post_init__(self) -> None:
        if self.total_seconds <= 0 or self.total_seconds > self.hard_max_seconds:
            raise ValueError("total_seconds must be positive")
        self.deadline_monotonic = self.started_monotonic + self.total_seconds

    # -------------------------------------------------------------------------
    def promote(self, profile: str) -> None:
        """Promote once from the initial budget to a bounded run profile."""

        requested = (
            min(self.simple_run_seconds, self.hard_max_seconds)
            if profile == "simple"
            else self.hard_max_seconds
        )
        requested = min(requested, self.hard_max_seconds)
        if requested <= self.total_seconds:
            self.run_profile = profile
            return
        self.total_seconds = requested
        self.deadline_monotonic = self.started_monotonic + requested
        self.run_profile = profile

    deadline_monotonic: float = field(init=False)

    # -------------------------------------------------------------------------
    def remaining_seconds(self) -> float:
        return max(0.0, self.deadline_monotonic - time.monotonic())

    # -------------------------------------------------------------------------
    def configure_limits(
        self,
        *,
        max_model_calls: int | None = None,
        max_tool_calls: int | None = None,
        max_state_transitions: int | None = None,
    ) -> None:
        """Attach the run's operation limits to this shared budget object."""

        for name, value in (
            ("max_model_calls", max_model_calls),
            ("max_tool_calls", max_tool_calls),
            ("max_state_transitions", max_state_transitions),
        ):
            if value is not None and value < 1:
                raise ValueError(f"{name} must be positive when configured")
        self.max_model_calls = max_model_calls
        self.max_tool_calls = max_tool_calls
        self.max_state_transitions = max_state_transitions

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
    def operation_timeout(
        self,
        stage: str,
        *,
        requested_seconds: float | None = None,
    ) -> float:
        """Return a child timeout bounded by both the stage and run deadline."""

        self.ensure_available(stage)
        limit = self.stage_limits.get(stage)
        if requested_seconds is not None:
            requested = max(0.0, float(requested_seconds))
            limit = requested if limit is None else min(limit, requested)
        remaining = self.remaining_seconds()
        if limit is None:
            return remaining
        return min(max(0.0, float(limit)), remaining)

    # -------------------------------------------------------------------------
    def record_model_call(self) -> None:
        self._ensure_counter_available(
            current=self.model_calls,
            limit=self.max_model_calls,
            reason="model_budget_exhausted",
            stage="model_call",
        )
        self.model_calls += 1

    # -------------------------------------------------------------------------
    def record_tool_call(self) -> None:
        self._ensure_counter_available(
            current=self.tool_calls,
            limit=self.max_tool_calls,
            reason="tool_budget_exhausted",
            stage="tool_call",
        )
        self.tool_calls += 1

    # -------------------------------------------------------------------------
    def record_transition(self) -> None:
        self._ensure_counter_available(
            current=self.state_transitions,
            limit=self.max_state_transitions,
            reason="transition_budget_exhausted",
            stage="state_transition",
        )
        self.state_transitions += 1

    # -------------------------------------------------------------------------
    def _ensure_counter_available(
        self,
        *,
        current: int,
        limit: int | None,
        reason: str,
        stage: str,
    ) -> None:
        if limit is not None and current >= limit:
            self.terminal_reason = reason
            raise ExecutionBudgetExceeded(reason, stage)

    # -------------------------------------------------------------------------
    def record_retry(self) -> None:
        self.retry_count += 1

    # -------------------------------------------------------------------------
    def record_context_allocation(self, allocation: dict[str, Any]) -> None:
        self.context_allocations.append(dict(allocation))

    # -------------------------------------------------------------------------
    def record_iteration(self, trace: dict[str, Any]) -> None:
        self.iteration_traces.append(dict(trace))

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
            if timeout_origin == "application_deadline":
                self.terminal_reason = self.terminal_reason or "run_deadline_exhausted"
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
            if status in {"failed", "timeout", "cancelled"}:
                self.terminal_stage = self.terminal_stage or stage

    # -------------------------------------------------------------------------
    def snapshot(self) -> dict[str, Any]:
        remaining_ms = max(0, int(self.remaining_seconds() * 1000))
        return {
            "total_budget_ms": int(self.total_seconds * 1000),
            "remaining_ms": remaining_ms,
            # Monotonic clocks cannot survive a process restart.  Keep a wall
            # clock deadline as a resume hint while in-process enforcement
            # continues to use the monotonic deadline.
            "deadline_epoch_ms": int(time.time() * 1000) + remaining_ms,
            "model_calls": self.model_calls,
            "tool_calls": self.tool_calls,
            "state_transitions": self.state_transitions,
            "max_model_calls": self.max_model_calls,
            "max_tool_calls": self.max_tool_calls,
            "max_state_transitions": self.max_state_transitions,
            "retry_count": self.retry_count,
            "terminal_reason": self.terminal_reason,
            "terminal_stage": self.terminal_stage,
            "run_profile": self.run_profile,
            "completion_requirements": list(self.completion_requirements),
            "stopping_reason": self.stopping_reason or self.terminal_reason,
            "context_allocations": list(self.context_allocations[-16:]),
            "iteration_traces": list(self.iteration_traces[-12:]),
            "stages": [item.to_dict() for item in self.observations[-32:]],
        }

    # -------------------------------------------------------------------------
    def restore_from_snapshot(self, snapshot: dict[str, Any]) -> None:
        """Restore bounded counters and deadline after a process restart."""

        def _nonnegative_int(name: str) -> int:
            value = snapshot.get(name, 0)
            return max(0, int(value)) if isinstance(value, (int, float)) else 0

        self.model_calls = _nonnegative_int("model_calls")
        self.tool_calls = _nonnegative_int("tool_calls")
        self.state_transitions = _nonnegative_int("state_transitions")
        self.retry_count = _nonnegative_int("retry_count")
        profile = snapshot.get("run_profile")
        if isinstance(profile, str) and profile in {"initial", "simple", "complex"}:
            self.run_profile = profile
        terminal_reason = snapshot.get("terminal_reason")
        self.terminal_reason = (
            terminal_reason if isinstance(terminal_reason, str) else None
        )
        terminal_stage = snapshot.get("terminal_stage")
        self.terminal_stage = terminal_stage if isinstance(terminal_stage, str) else None
        stopping_reason = snapshot.get("stopping_reason")
        self.stopping_reason = (
            stopping_reason if isinstance(stopping_reason, str) else None
        )
        allocations = snapshot.get("context_allocations")
        if isinstance(allocations, list):
            self.context_allocations = [
                dict(item) for item in allocations if isinstance(item, dict)
            ][-16:]
        iterations = snapshot.get("iteration_traces")
        if isinstance(iterations, list):
            self.iteration_traces = [
                dict(item) for item in iterations if isinstance(item, dict)
            ][-12:]

        deadline_epoch_ms = snapshot.get("deadline_epoch_ms")
        if isinstance(deadline_epoch_ms, (int, float)):
            remaining_seconds = max(
                0.0, (float(deadline_epoch_ms) - time.time() * 1000) / 1000.0
            )
        else:
            remaining_seconds = max(
                0.0, float(snapshot.get("remaining_ms") or 0) / 1000.0
            )
        self.total_seconds = min(
            self.hard_max_seconds,
            max(0.001, float(snapshot.get("total_budget_ms") or 0) / 1000.0),
        )
        self.started_monotonic = time.monotonic()
        self.deadline_monotonic = self.started_monotonic + remaining_seconds
