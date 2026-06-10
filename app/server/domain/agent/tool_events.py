from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolLoopStarted:
    provider: str
    model: str
    tool_count: int


@dataclass(frozen=True)
class ToolCallRequested:
    tool_name: str
    iteration: int
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolCallAuthorized:
    tool_name: str
    iteration: int


@dataclass(frozen=True)
class ToolCallRejected:
    tool_name: str
    iteration: int
    reason: str


@dataclass(frozen=True)
class ToolCallExecuted:
    tool_name: str
    iteration: int
    latency_ms: int
    success: bool
    error_code: str | None = None


@dataclass(frozen=True)
class ToolLoopCompleted:
    provider: str
    model: str
    iterations: int
    stopped_reason: str


@dataclass(frozen=True)
class ToolLoopFailed:
    provider: str
    model: str
    reason: str
