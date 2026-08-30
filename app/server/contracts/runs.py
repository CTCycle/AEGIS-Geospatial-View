from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_validator


###############################################################################
class AgentRunState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    UPDATING = "updating"
    WAITING_FOR_CLARIFICATION = "waiting_for_clarification"
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
class AgentRunCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str
    client_request_id: str | None = None

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
    started_at: datetime | None = None
    completed_at: datetime | None = None
    cancel_requested_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None


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
