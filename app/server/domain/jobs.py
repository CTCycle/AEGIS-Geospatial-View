from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

BackgroundJobType = Literal["chat_turn", "map_fetch"]
BackgroundJobStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]
BackgroundJobEventType = Literal[
    "queued",
    "started",
    "status",
    "parsed",
    "policy",
    "tool_call",
    "tool_result",
    "map_session",
    "completed",
    "failed",
    "cancelled",
]


class BackgroundJobCreateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    job_type: BackgroundJobType
    status: BackgroundJobStatus
    request_id: str
    message: str
    poll_interval: float = 1.0


class BackgroundJobEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    event_type: BackgroundJobEventType
    sequence: int
    created_at: datetime
    payload_json: dict[str, Any] = Field(default_factory=dict)


class BackgroundJobStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    job_type: BackgroundJobType
    status: BackgroundJobStatus
    request_id: str
    parent_job_id: str | None = None
    session_id: int | None = None
    priority: int = 0
    progress_percent: int | None = None
    status_message: str | None = None
    result_json: dict[str, Any] | None = None
    error_json: dict[str, Any] | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    cancel_requested_at: datetime | None = None
    attempt_count: int = 0
    max_attempts: int = 1
    last_heartbeat_at: datetime | None = None


class BackgroundJobEventsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    events: list[BackgroundJobEvent] = Field(default_factory=list)


class JobCancelResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    success: bool
    message: str


JobStartResponse = BackgroundJobCreateResponse
JobStatusResponse = BackgroundJobStatusResponse


from dataclasses import dataclass, field  # noqa: E402
from time import monotonic  # noqa: E402


@dataclass
class BackgroundJobState:
    job_id: str
    job_type: str
    status: str = "queued"
    progress: float = 0.0
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: float = field(default_factory=monotonic)
    completed_at: float | None = None
    stop_requested: bool = False


from datetime import UTC  # noqa: E402


@dataclass
class BackgroundJob:
    job_id: str
    job_type: str
    request_id: str
    input_json: dict[str, Any]
    parent_job_id: str | None = None
    session_id: int | None = None
    status: str = "queued"
    priority: int = 0
    progress_percent: int | None = 0
    status_message: str | None = "Queued"
    result_json: dict[str, Any] | None = None
    error_json: dict[str, Any] | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    cancel_requested_at: datetime | None = None
    attempt_count: int = 0
    max_attempts: int = 1
    last_heartbeat_at: datetime | None = None
    events: list["BackgroundJobEvent"] = field(default_factory=list)
