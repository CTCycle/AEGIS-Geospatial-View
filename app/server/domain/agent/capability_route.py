"""Typed routing and working-state contracts for the native agent loop.

The legacy agent keeps its parser and planner contracts for now.  These models
are deliberately independent of those services so the native-v2 path can be
introduced and tested without making the model responsible for provider or
MapLibre implementation details.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from server.contracts.geospatial import MapSession
from server.domain.agent.capability_domains import CapabilityDomain
from server.domain.agent.decision import ResolvedLocation
from server.domain.agent.interpretation import CanonicalRequestInterpretation
from server.domain.agent.tool_result import ToolResult

###############################################################################
class CapabilityRoute(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary_domain: CapabilityDomain
    secondary_domains: list[CapabilityDomain] = Field(default_factory=list, max_length=3)
    task_mode: Literal["answer", "execute", "clarify"]
    presentation: Literal["text", "map", "both"]
    requires_location: bool
    capability_queries: list[str] = Field(default_factory=list, max_length=4)
    explicit_capability_ids: list[str] = Field(default_factory=list, max_length=8)
    clarification_question: str | None = Field(default=None, max_length=500)
    # These are user-semantic constraints, not provider arguments.  Keeping
    # them on the validated route gives the native harness a deterministic
    # request contract even when the legacy parser is not involved.
    operation: str | None = Field(default=None, min_length=1, max_length=80)
    target_refs: list[str] = Field(default_factory=list, max_length=16)
    temporal_scope: "AgentTemporalScope" = Field(default_factory=lambda: AgentTemporalScope())
    spatial_scope: "AgentSpatialScope | None" = None
    filters: dict[str, Any] = Field(default_factory=dict)


class AgentTemporalScope(BaseModel):
    """Provider-neutral temporal intent selected during route bootstrap."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["current", "historical", "forecast", "none"] = "none"
    reference_time_iso: str | None = Field(default=None, max_length=80)
    start_time_iso: str | None = Field(default=None, max_length=80)
    end_time_iso: str | None = Field(default=None, max_length=80)
    granularity: str = Field(default="none", max_length=40)
    aggregation: str = Field(default="none", max_length=40)


class AgentSpatialScope(BaseModel):
    """Provider-neutral spatial intent; coordinates remain server-owned."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal[
        "point",
        "bbox",
        "radius",
        "administrative_geometry",
        "feature_geometry",
        "viewport",
    ]
    relationship: Literal[
        "at",
        "in",
        "near",
        "around",
        "within_distance",
        "along",
        "visible_area",
        "here",
    ] = "at"
    target_refs: list[str] = Field(default_factory=list, max_length=16)
    distance_m: float | None = Field(default=None, gt=0.0, le=1_000_000)


CapabilityRoute.model_rebuild()

###############################################################################
class AgentGoal(BaseModel):
    """Server-owned goal details derived from a validated native route."""

    model_config = ConfigDict(extra="forbid")

    goal: str
    task_mode: Literal["answer", "execute", "clarify"]
    presentation: Literal["text", "map", "both"]
    operation: str
    requires_location: bool
    target_ids: list[str] = Field(default_factory=list, max_length=16)
    temporal_scope: dict[str, object] = Field(default_factory=dict)
    spatial_scope: list[dict[str, object]] = Field(default_factory=list, max_length=16)
    filters: dict[str, object] = Field(default_factory=dict)


class CompletionContract(BaseModel):
    """Deterministic obligations the native loop must satisfy."""

    model_config = ConfigDict(extra="forbid")

    operation: str
    requirements: list[str] = Field(default_factory=list, max_length=16)
    location_required: bool = False
    evidence_required: bool = False
    map_preparation_required: bool = False
    temporal_scope_required: bool = False
    spatial_scope_required: bool = False

###############################################################################
class CapabilityRouteDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal[
        "accepted",
        "clarification",
        "no_capability",
        "discovery_required",
        "rejected",
    ]
    route: CapabilityRoute
    capability_ids: list[str] = Field(default_factory=list, max_length=12)
    rejected_capability_ids: list[str] = Field(default_factory=list, max_length=8)
    reason_codes: list[str] = Field(default_factory=list, max_length=16)
    clarification_question: str | None = Field(default=None, max_length=500)

###############################################################################
class AgentPhase(StrEnum):
    RECEIVE_REQUEST = "receive_request"
    ROUTE_REQUEST = "route_request"
    BUILD_TOOL_CONTEXT = "build_tool_context"
    MODEL_STEP = "model_step"
    VALIDATE_ACTION = "validate_action"
    EXECUTE_TOOL = "execute_tool"
    NORMALIZE_RESULT = "normalize_result"
    UPDATE_STATE = "update_state"
    EVALUATE_STOP = "evaluate_stop"
    AWAIT_RENDER = "await_render"
    FINALIZE = "finalize"
    FAILED = "failed"

###############################################################################
class AgentState(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    request_id: str
    run_id: str | None = None
    conversation_id: str
    phase: AgentPhase
    user_message: str
    goal: AgentGoal | None = None
    completion_contract: CompletionContract | None = None
    completion_requirements: list[str] = Field(default_factory=list)
    active_instructions: list[dict[str, object]] = Field(default_factory=list)
    task_state: dict[str, object] = Field(default_factory=dict)
    map_memory: dict[str, object] = Field(default_factory=dict)
    conversation_summary: dict[str, object] | None = None
    recent_messages: list[dict[str, object]] = Field(default_factory=list)
    relevant_tool_outcomes: list[dict[str, object]] = Field(default_factory=list)
    policy_constraints: dict[str, object] = Field(default_factory=dict)
    included_message_ids: list[int] = Field(default_factory=list)
    omitted_message_ids: list[int] = Field(default_factory=list)
    summarized_through_turn_index: int = 0
    context_allocation: dict[str, object] = Field(default_factory=dict)
    context_hydrated: bool = False
    route: CapabilityRoute | None = None
    capability_ids: list[str] = Field(default_factory=list)
    location_refs: dict[str, ResolvedLocation] = Field(default_factory=dict)
    evidence_refs: list[str] = Field(default_factory=list)
    active_map_session: MapSession | None = None
    prepared_map_session: MapSession | None = None
    canonical_request: CanonicalRequestInterpretation | None = None
    tool_results: list[ToolResult] = Field(default_factory=list)
    successful_fingerprints: dict[str, ToolResult] = Field(default_factory=dict)
    failed_fingerprints: dict[str, int] = Field(default_factory=dict)
    consecutive_tool_failures: int = Field(default=0, ge=0)
    route_corrections: int = Field(default=0, ge=0)
    validation_corrections: int = Field(default=0, ge=0)
    model_calls: int = Field(default=0, ge=0)
    tool_calls: int = Field(default=0, ge=0)
    transitions: int = Field(default=0, ge=0)
    transition_trace: list[dict[str, str]] = Field(default_factory=list)
    exposure_trace: list[dict[str, str]] = Field(default_factory=list)
    discovery_attempts: int = Field(default=0, ge=0)
    termination_reason: str | None = None
