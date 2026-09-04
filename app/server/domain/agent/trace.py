from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from server.common.time import utc_now


TraceKind = Literal[
    "run_started",
    "plan_created",
    "plan_revised",
    "task_transition",
    "tools_available",
    "tool_selected",
    "tool_result",
    "retry",
    "state_delta",
    "checkpoint",
    "model_usage",
    "stage",
    "completion",
]


###############################################################################
class AgentTraceEvent(BaseModel):
    """Operational trace metadata; never a chain-of-thought transcript."""

    model_config = ConfigDict(extra="forbid")

    kind: TraceKind
    run_id: str
    run_version: int = Field(ge=1)
    sequence: int = Field(ge=0)
    timestamp: datetime = Field(default_factory=utc_now)
    task_id: str | None = None
    tool_name: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


###############################################################################
class AgentCheckpoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[2] = 2
    run_id: str
    conversation_id: str
    run_version: int = Field(ge=1)
    task_snapshot: dict[str, Any]
    state_hash: str
    completed_call_fingerprints: list[str] = Field(default_factory=list)
    completion_reason: str | None = None
