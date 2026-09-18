from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from server.contracts.geospatial import MapSession
from server.domain.agent.conversation import ConversationState
from server.domain.agent.capability_route import AgentTaskState

###############################################################################
class AgentRunState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    UPDATING = "updating"
    WAITING_FOR_CLARIFICATION = "waiting_for_clarification"
    AWAITING_RENDER = "awaiting_render"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_RUN_STATES = {
    AgentRunState.COMPLETED,
    AgentRunState.FAILED,
    AgentRunState.CANCELLED,
}

###############################################################################
class ConversationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = None

###############################################################################
class ConversationCreateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation_id: str
    title: str | None = None

###############################################################################
class ConversationMessageSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant", "system", "tool"]
    content: str
    created_at: datetime

###############################################################################
class ActiveConversationRunSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    run_version: int = Field(..., ge=1)
    state: AgentRunState
    presentation_status: Literal["not_required", "pending", "ready", "failed", "render_timeout"] = "not_required"
    presentation: dict[str, Any] | None = None
    current_iteration: int | None = Field(default=None, ge=0)
    task_state: AgentTaskState | None = None


###############################################################################
class ConversationRunSummary(BaseModel):
    """Bounded operational summary of one persisted native run."""

    model_config = ConfigDict(extra="forbid")

    conversation_id: str
    run_id: str
    run_version: int = Field(..., ge=1)
    active_run_version: int = Field(..., ge=1)
    original_request: str
    aggregated_request: str
    state: AgentRunState
    request_timezone: str | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    cancel_requested_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None
    presentation_status: Literal[
        "not_required", "pending", "ready", "failed", "render_timeout"
    ] = "not_required"
    duration_ms: int | None = Field(default=None, ge=0)
    current_iteration: int | None = Field(default=None, ge=0)
    task_state: AgentTaskState | None = None


###############################################################################
class ConversationSummary(BaseModel):
    """Searchable, bounded conversation listing item."""

    model_config = ConfigDict(extra="forbid")

    conversation_id: str
    title: str | None = None
    context_revision: int = Field(..., ge=0)
    message_count: int = Field(default=0, ge=0)
    last_message_preview: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    active_run: ActiveConversationRunSnapshot | None = None
    latest_run: ConversationRunSummary | None = None


###############################################################################
class ConversationListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversations: list[ConversationSummary] = Field(
        default_factory=lambda: list[ConversationSummary]()
    )
    next_cursor: str | None = None
    has_more: bool = False
    total: int = Field(default=0, ge=0)
    pagination: dict[str, Any] = Field(
        default_factory=lambda: dict[str, Any]()
    )


###############################################################################
class RunTraceEntry(BaseModel):
    """Redacted operational trace row; never a chain-of-thought contract."""

    model_config = ConfigDict(extra="forbid")

    event_id: str
    sequence: int = Field(..., ge=1)
    conversation_id: str
    run_id: str
    run_version: int = Field(..., ge=1)
    type: str
    visibility: Literal["user", "internal"]
    timestamp: datetime
    kind: str
    task_id: str | None = None
    tool_name: str | None = None
    call_id: str | None = None
    iteration: int | None = Field(default=None, ge=1)
    label: str | None = None
    status: str | None = None
    summary: str | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    evidence_refs: list[str] = Field(default_factory=lambda: list[str]())
    retryable: bool | None = None
    error: Any | None = None
    payload: dict[str, Any] = Field(default_factory=lambda: dict[str, Any]())


###############################################################################
class RunTraceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation_id: str
    run_id: str
    run_version: int | None = Field(default=None, ge=1)
    events: list[RunTraceEntry] = Field(
        default_factory=lambda: list[RunTraceEntry]()
    )
    next_cursor: str | None = None
    has_more: bool = False
    total: int = Field(default=0, ge=0)
    pagination: dict[str, Any] = Field(
        default_factory=lambda: dict[str, Any]()
    )

    @property
    def entries(self) -> list[RunTraceEntry]:
        """Alias for clients that call trace rows entries."""

        return self.events

###############################################################################
class ConversationSnapshotResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation_id: str
    title: str | None = None
    context_revision: int = Field(..., ge=0)
    messages: list[ConversationMessageSnapshot] = Field(
        default_factory=lambda: list[ConversationMessageSnapshot]()
    )
    conversation_state: ConversationState
    memory_snapshot: dict[str, Any] = Field(default_factory=dict)
    map_session: MapSession | None = None
    active_run: ActiveConversationRunSnapshot | None = None
    recent_runs: list[ConversationRunSummary] = Field(
        default_factory=lambda: list[ConversationRunSummary]()
    )

###############################################################################
class AgentRunCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str
    client_request_id: str | None = None
    timezone: str | None = Field(default=None, max_length=64)

    # -------------------------------------------------------------------------
    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("message must not be empty")
        if len(normalized) > 12000:
            raise ValueError("message is too long")
        return normalized

    # -------------------------------------------------------------------------
    @field_validator("client_request_id")
    @classmethod
    def normalize_client_request_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        if len(normalized) > 160:
            raise ValueError("client_request_id is too long")
        return normalized

###############################################################################
class AgentRunCreateResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation_id: str
    run_id: str
    run_version: int
    state: AgentRunState

###############################################################################
class AgentRunSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation_id: str
    run_id: str
    original_request: str
    aggregated_request: str
    active_run_version: int
    state: AgentRunState
    created_at: datetime
    request_timezone: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    cancel_requested_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None
    presentation_status: Literal["not_required", "pending", "ready", "failed", "render_timeout"] = "not_required"
    presentation: dict[str, Any] | None = None
    response: dict[str, Any] | None = None
    current_iteration: int | None = Field(default=None, ge=0)
    task_state: AgentTaskState | None = None

###############################################################################
class AgentRunCancelResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation_id: str
    run_id: str
    state: AgentRunState
    cancel_requested_at: datetime | None = None

###############################################################################
class ActiveRunContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation_id: str
    run_id: str
    run_version: int
    aggregated_request: str
    cancel_requested: bool = False
