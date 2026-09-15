"""Typed routing, goal, and run-state contracts for the native agent."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from server.contracts.geospatial import MapSession
from server.domain.agent.capability_domains import CapabilityDomain
from server.domain.agent.decision import ResolvedLocation
from server.domain.agent.tool_result import ModelObservation, ToolResult

###############################################################################
class CapabilityRoute(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary_domain: CapabilityDomain
    secondary_domains: list[CapabilityDomain] = Field(
        default_factory=lambda: list[CapabilityDomain](), max_length=3
    )
    task_mode: Literal["answer", "execute", "clarify"]
    presentation: Literal["text", "map", "both"]
    requires_location: bool
    capability_queries: list[str] = Field(
        default_factory=lambda: list[str](), max_length=4
    )
    explicit_capability_ids: list[str] = Field(
        default_factory=lambda: list[str](), max_length=8
    )
    clarification_question: str | None = Field(default=None, max_length=500)
    # These are user-semantic constraints, not provider arguments.  Keeping
    # them on the validated route gives the native harness a deterministic
    # request contract without a separate interpretation stage.
    operation: str | None = Field(default=None, min_length=1, max_length=80)
    target_refs: list[str] = Field(default_factory=lambda: list[str](), max_length=16)
    temporal_scope: "AgentTemporalScope" = Field(default_factory=lambda: AgentTemporalScope())
    spatial_scope: "AgentSpatialScope | None" = None
    filters: dict[str, Any] = Field(default_factory=lambda: dict[str, Any]())


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
    target_refs: list[str] = Field(default_factory=lambda: list[str](), max_length=16)
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
    target_ids: list[str] = Field(default_factory=lambda: list[str](), max_length=16)
    temporal_scope: dict[str, object] = Field(
        default_factory=lambda: dict[str, object]()
    )
    spatial_scope: list[dict[str, object]] = Field(
        default_factory=lambda: list[dict[str, object]](), max_length=16
    )
    filters: dict[str, object] = Field(
        default_factory=lambda: dict[str, object]()
    )


class CompletionContract(BaseModel):
    """Deterministic obligations the native loop must satisfy."""

    model_config = ConfigDict(extra="forbid")

    operation: str
    requirements: list[str] = Field(
        default_factory=lambda: list[str](), max_length=16
    )
    location_required: bool = False
    evidence_required: bool = False
    map_preparation_required: bool = False
    temporal_scope_required: bool = False
    spatial_scope_required: bool = False


CompletionStatus = Literal["pending", "satisfied", "failed", "not_applicable"]


class CompletionRequirement(BaseModel):
    """One server-owned obligation in a native run or render handshake."""

    model_config = ConfigDict(extra="forbid")

    name: str
    required: bool = True
    status: CompletionStatus = "pending"
    target_id: str | None = None
    evidence_ref: str | None = None
    failure_code: str | None = None

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
    capability_ids: list[str] = Field(
        default_factory=lambda: list[str](), max_length=12
    )
    rejected_capability_ids: list[str] = Field(
        default_factory=lambda: list[str](), max_length=8
    )
    reason_codes: list[str] = Field(
        default_factory=lambda: list[str](), max_length=16
    )
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
class AgentRunState(BaseModel):
    """Canonical mutable/checkpointable state for one native agent run."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    schema_version: Literal[1] = 1
    request_id: str
    run_id: str | None = None
    run_version: int = Field(default=1, ge=1)
    conversation_revision: int = Field(default=0, ge=0)
    conversation_id: str
    phase: AgentPhase
    user_message: str
    goal: AgentGoal | None = None
    completion_contract: CompletionContract | None = None
    completion_requirements: list[str] = Field(default_factory=lambda: list[str]())
    active_directives: list[dict[str, object]] = Field(
        default_factory=lambda: list[dict[str, object]]()
    )
    task_state: dict[str, object] = Field(
        default_factory=lambda: dict[str, object]()
    )
    map_memory: dict[str, object] = Field(
        default_factory=lambda: dict[str, object]()
    )
    summary: dict[str, object] | None = None
    recent_messages: list[dict[str, object]] = Field(
        default_factory=lambda: list[dict[str, object]]()
    )
    relevant_tool_outcomes: list[dict[str, object]] = Field(
        default_factory=lambda: list[dict[str, object]]()
    )
    policy_constraints: dict[str, object] = Field(
        default_factory=lambda: dict[str, object]()
    )
    included_message_ids: list[int] = Field(default_factory=lambda: list[int]())
    omitted_message_ids: list[int] = Field(default_factory=lambda: list[int]())
    summarized_through_turn_index: int = 0
    context_allocation: dict[str, object] = Field(
        default_factory=lambda: dict[str, object]()
    )
    context_usage_trace: list[dict[str, object]] = Field(
        default_factory=lambda: list[dict[str, object]]()
    )
    model_trace: list[dict[str, object]] = Field(
        default_factory=lambda: list[dict[str, object]]()
    )
    tool_trace: list[dict[str, object]] = Field(
        default_factory=lambda: list[dict[str, object]]()
    )
    # Provider protocol items are retained only for continuation/resume. They
    # are never used as the semantic state view.
    provider_continuation: list[dict[str, object]] = Field(
        default_factory=lambda: list[dict[str, object]]()
    )
    context_hydrated: bool = False
    route: CapabilityRoute | None = None
    capability_ids: list[str] = Field(default_factory=lambda: list[str]())
    excluded_capability_ids: list[str] = Field(
        default_factory=lambda: list[str](), max_length=32
    )
    location_refs: dict[str, ResolvedLocation] = Field(
        default_factory=lambda: dict[str, ResolvedLocation]()
    )
    evidence_refs: list[str] = Field(default_factory=lambda: list[str]())
    active_map_session: MapSession | None = None
    prepared_map_session: MapSession | None = None
    tool_results: list[ToolResult] = Field(default_factory=lambda: list[ToolResult]())
    successful_fingerprints: dict[str, ToolResult] = Field(
        default_factory=lambda: dict[str, ToolResult]()
    )
    failed_fingerprints: dict[str, int] = Field(
        default_factory=lambda: dict[str, int]()
    )
    consecutive_tool_failures: int = Field(default=0, ge=0)
    route_corrections: int = Field(default=0, ge=0)
    validation_corrections: int = Field(default=0, ge=0)
    model_calls: int = Field(default=0, ge=0)
    tool_calls: int = Field(default=0, ge=0)
    transitions: int = Field(default=0, ge=0)
    transition_trace: list[dict[str, str]] = Field(
        default_factory=lambda: list[dict[str, str]]()
    )
    exposure_trace: list[dict[str, str]] = Field(
        default_factory=lambda: list[dict[str, str]]()
    )
    discovery_attempts: int = Field(default=0, ge=0)
    budget_snapshot: dict[str, object] = Field(
        default_factory=lambda: dict[str, object]()
    )
    termination_reason: str | None = None

    def checkpoint(self) -> dict[str, Any]:
        """Return a bounded JSON-safe checkpoint for durable resume."""

        payload = self.model_dump(mode="json")
        payload["tool_results"] = [
            _checkpoint_tool_result(item) for item in self.tool_results[-16:]
        ]
        payload["successful_fingerprints"] = {
            key: _checkpoint_tool_result(value)
            for key, value in list(self.successful_fingerprints.items())[-32:]
        }
        payload["recent_messages"] = list(self.recent_messages[-64:])
        payload["relevant_tool_outcomes"] = list(self.relevant_tool_outcomes[-32:])
        payload["context_usage_trace"] = list(self.context_usage_trace[-16:])
        payload["model_trace"] = list(self.model_trace[-16:])
        payload["tool_trace"] = list(self.tool_trace[-32:])
        payload["transition_trace"] = list(self.transition_trace[-64:])
        payload["exposure_trace"] = list(self.exposure_trace[-64:])
        payload["provider_continuation"] = list(self.provider_continuation[-16:])
        return payload

    @classmethod
    def from_checkpoint(cls, payload: dict[str, Any]) -> "AgentRunState":
        """Restore one validated native run checkpoint."""

        return cls.model_validate(payload)


def _checkpoint_tool_result(value: ToolResult) -> dict[str, Any]:
    """Keep model-facing result data without embedding raw provider payloads."""

    observation = ModelObservation.from_tool_result(value, max_chars=4096)
    return value.model_copy(update={"data": observation.result}, deep=True).model_dump(
        mode="json"
    )
