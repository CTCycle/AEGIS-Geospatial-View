"""Contracts for bounded, conversation-scoped agent evidence.

The native loop exchanges references and compact summaries.  Provider payloads
stay behind the evidence repository boundary so model context, traces, and chat
history never become an unbounded data transport.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

EvidenceStatus = Literal["available", "partial", "valid_empty", "failed", "superseded"]
EvidenceKind = Literal[
    "location",
    "capability_result",
    "provider_layer_descriptor",
    "vector",
    "tabular",
    "raster_descriptor",
    "derived",
    "diagnostic",
]


class AgentEvidenceSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    kind: EvidenceKind
    media_type: str
    status: EvidenceStatus
    summary: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)
    parent_evidence_ids: list[str] = Field(default_factory=list)
    byte_size: int = Field(default=0, ge=0)
    sha256: str | None = None
    map_eligibility: Literal["renderable", "not_renderable", "unknown"] = "unknown"


class AgentEvidenceEnvelope(BaseModel):
    """Normalized result shape returned to the model for every evidence call."""

    model_config = ConfigDict(extra="forbid")

    ok: bool
    status: EvidenceStatus | Literal["error"]
    evidence_ref: str | None = None
    summary: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)
    map_eligibility: Literal["renderable", "not_renderable", "unknown"] = "unknown"
    error: dict[str, Any] | None = None
    pagination: dict[str, Any] | None = None
    state_changes: list[dict[str, Any]] = Field(default_factory=list)


class AgentContextAllocation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phase: Literal["parser", "native_loop", "synthesis"]
    model: str
    estimator_source: str
    usable_input_tokens: int = Field(ge=0)
    mandatory_tokens: int = Field(default=0, ge=0)
    evidence_tokens: int = Field(default=0, ge=0)
    conversation_tokens: int = Field(default=0, ge=0)
    summary_tokens: int = Field(default=0, ge=0)
    response_reserve_tokens: int = Field(default=0, ge=0)
    safety_tokens: int = Field(default=512, ge=0)
    compacted_ids: list[str] = Field(default_factory=list)
    mandatory_overflow: bool = False


class AgentWorkingState(BaseModel):
    """Typed state rebuilt before each native decision."""

    model_config = ConfigDict(extra="forbid")

    goal: str = ""
    explicit_constraints: dict[str, Any] = Field(default_factory=dict)
    active_directives: list[dict[str, Any]] = Field(default_factory=list)
    canonical_request: dict[str, Any] = Field(default_factory=dict)
    resolved_locations: list[dict[str, Any]] = Field(default_factory=list)
    task_ledger: dict[str, Any] = Field(default_factory=dict)
    completion_requirements: list[str] = Field(default_factory=list)
    render_status: str = "not_required"
    capability_domains: list[str] = Field(default_factory=list)
    routing_reasons: list[str] = Field(default_factory=list)
    evidence: list[AgentEvidenceSummary] = Field(default_factory=list)
    relevant_errors: list[dict[str, Any]] = Field(default_factory=list)
    retries: list[dict[str, Any]] = Field(default_factory=list)
    active_map_revision: str | None = None
    presentation_state: dict[str, Any] = Field(default_factory=dict)
    available_tools: list[str] = Field(default_factory=list)
    tool_exposure_reasons: dict[str, str] = Field(default_factory=dict)
    context_budget: AgentContextAllocation | None = None


class AgentIterationTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    iteration: int = Field(ge=1)
    execution_mode: Literal["native", "deterministic"]
    available_tools: list[str] = Field(default_factory=list)
    tool_exposure_reasons: dict[str, str] = Field(default_factory=dict)
    selected_tool: str | None = None
    capability_id: str | None = None
    started_at: str
    duration_ms: int = Field(default=0, ge=0)
    result_status: str
    evidence_refs: list[str] = Field(default_factory=list)
    state_changes: list[dict[str, Any]] = Field(default_factory=list)
    pending_requirements: list[str] = Field(default_factory=list)
    retry_number: int = Field(default=0, ge=0)
    context_usage: dict[str, Any] = Field(default_factory=dict)
    stopping_evaluation: dict[str, Any] | None = None


class AgentStopEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposed: bool
    satisfied: bool
    reason: Literal[
        "goal_satisfied",
        "awaiting_render",
        "clarification_required",
        "insufficient_evidence",
        "provider_error",
        "context_limit",
        "tool_budget_exhausted",
        "run_deadline_exhausted",
        "no_progress",
        "cancelled",
        "superseded",
    ]
    pending_requirements: list[str] = Field(default_factory=list)
    useful_tools: list[str] = Field(default_factory=list)
