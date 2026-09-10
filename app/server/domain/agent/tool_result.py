"""Canonical model-visible tool result contracts for native-v2."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


ToolErrorType = Literal[
    "malformed_call",
    "unknown_tool",
    "schema_validation",
    "semantic_validation",
    "policy_rejection",
    "state_conflict",
    "timeout",
    "rate_limit",
    "authentication",
    "provider_unavailable",
    "provider_malformed_response",
    "invalid_tool_output",
    "internal_error",
]
ToolRecovery = Literal[
    "correct_arguments",
    "retry_transport",
    "choose_alternate_tool",
    "replan",
    "request_user_input",
    "terminal",
]


###############################################################################
class ValidationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    code: str
    message: str


###############################################################################
class ToolExecutionError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error_type: ToolErrorType
    code: str
    message: str
    retryable: bool
    recovery: ToolRecovery
    validation_errors: list[ValidationIssue] = Field(default_factory=list)
    upstream_status: int | None = Field(default=None, ge=100, le=599)
    timeout_origin: str | None = None


###############################################################################
class ToolExecutionMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capability_id: str | None = None
    provider_id: str | None = None
    attempt: int = Field(default=1, ge=1)
    duration_ms: int = Field(ge=0)
    api_latency_ms: int | None = Field(default=None, ge=0)
    result_size_bytes: int | None = Field(default=None, ge=0)
    evidence_refs: list[str] = Field(default_factory=list)


###############################################################################
class ToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    call_id: str
    tool_name: str
    status: Literal["success", "valid_empty", "partial", "failed"]
    summary: str
    data: dict[str, Any] | list[Any] | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    map_candidate_id: str | None = None
    error: ToolExecutionError | None = None
    metadata: ToolExecutionMetadata
    truncated: bool = False
    continuation: str | None = None
