from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from server.common.time import utc_now

###############################################################################
class RunEventType(StrEnum):
    PROGRESS = "progress"
    ASSISTANT_TEXT_DELTA = "assistant_text_delta"
    ASSISTANT_TEXT_COMPLETED = "assistant_text_completed"
    TOOL_STARTED = "tool_started"
    TOOL_COMPLETED = "tool_completed"
    REQUEST_UPDATED = "request_updated"
    ERROR = "error"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    CLARIFICATION_NEEDED = "clarification_needed"

###############################################################################
class RunEventVisibility(StrEnum):
    USER = "user"
    INTERNAL = "internal"

###############################################################################
class RunProgressStage(StrEnum):
    AGENT_STARTED = "agent_started"
    UNDERSTANDING_REQUEST = "understanding_request"
    RETRIEVING_INFORMATION = "retrieving_information"
    CALLING_TOOL = "calling_tool"
    PROCESSING_TOOL_RESULTS = "processing_tool_results"
    DRAFTING_ANSWER = "drafting_answer"
    REQUEST_UPDATED = "request_updated"
    WAITING_FOR_CLARIFICATION = "waiting_for_clarification"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


RUN_PROGRESS_LABELS: dict[RunProgressStage, str] = {
    RunProgressStage.AGENT_STARTED: "AEGIS agent started",
    RunProgressStage.UNDERSTANDING_REQUEST: "Understanding the request",
    RunProgressStage.RETRIEVING_INFORMATION: "Searching or retrieving information",
    RunProgressStage.CALLING_TOOL: "Calling a relevant tool",
    RunProgressStage.PROCESSING_TOOL_RESULTS: "Processing tool results",
    RunProgressStage.DRAFTING_ANSWER: "Drafting the answer",
    RunProgressStage.REQUEST_UPDATED: "Request updated because of user steering",
    RunProgressStage.WAITING_FOR_CLARIFICATION: "Waiting for clarification",
    RunProgressStage.COMPLETED: "Completed",
    RunProgressStage.FAILED: "Failed",
    RunProgressStage.CANCELLED: "Cancelled",
}

###############################################################################
class RunEventPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

###############################################################################
class RunEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    sequence: int
    conversation_id: str
    run_id: str
    run_version: int
    type: RunEventType
    timestamp: datetime
    visibility: RunEventVisibility
    payload: dict[str, Any] = Field(default_factory=dict)

###############################################################################
class RunEventCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation_id: str
    run_id: str
    run_version: int
    type: RunEventType
    visibility: RunEventVisibility = RunEventVisibility.USER
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=utc_now)

###############################################################################
class RunEventStreamResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    events: list[RunEvent]
    visibility: Literal["user", "internal"] = "user"
