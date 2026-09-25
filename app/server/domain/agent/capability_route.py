"""Typed routing, goal, and run-state contracts for the native agent."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal, cast

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


###############################################################################
class AgentTemporalScope(BaseModel):
    """Provider-neutral temporal intent selected during route bootstrap."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["current", "historical", "forecast", "none"] = "none"
    reference_time_iso: str | None = Field(default=None, max_length=80)
    start_time_iso: str | None = Field(default=None, max_length=80)
    end_time_iso: str | None = Field(default=None, max_length=80)
    granularity: str = Field(default="none", max_length=40)
    aggregation: str = Field(default="none", max_length=40)


###############################################################################
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


###############################################################################
class CompletionContract(BaseModel):
    """Deterministic obligations the native loop must satisfy."""

    model_config = ConfigDict(extra="forbid")

    operation: str
    data_requirement: Literal["none", "provider_data"] = "none"
    requirements: list[str] = Field(
        default_factory=lambda: list[str](), max_length=16
    )
    location_required: bool = False
    evidence_required: bool = False
    map_preparation_required: bool = False
    temporal_scope_required: bool = False
    spatial_scope_required: bool = False
    render_verification_required: bool = False
    render_verified: bool = False


CompletionStatus = Literal["pending", "satisfied", "failed", "not_applicable"]
CompletionRequirementKind = Literal[
    "location",
    "capability_discovery",
    "provider_data",
    "evidence_inspection",
    "temporal_scope",
    "spatial_scope",
    "map_candidate",
    "render_ack",
    "final_text",
]


###############################################################################
class CompletionRequirement(BaseModel):
    """One server-owned obligation in a native run or render handshake."""

    model_config = ConfigDict(extra="forbid")

    name: str
    kind: CompletionRequirementKind | None = None
    required: bool = True
    status: CompletionStatus = "pending"
    target_id: str | None = None
    evidence_ref: str | None = None
    failure_code: str | None = None

###############################################################################
class RenderObservation(BaseModel):
    """Bounded browser observation returned to the native agent state."""

    model_config = ConfigDict(extra="forbid")

    map_session_id: str = Field(min_length=1, max_length=160)
    collection_revision: int = Field(ge=0)
    attempt: int = Field(ge=1, le=32)
    status: Literal["ready", "failed"]
    viewport_bounds: list[float] | None = Field(default=None, max_length=4)
    checks: dict[str, bool] = Field(default_factory=lambda: dict[str, bool](), max_length=32)
    overlay_results: list[dict[str, object]] = Field(
        default_factory=lambda: list[dict[str, object]](), max_length=64
    )
    failure_code: str | None = Field(default=None, max_length=120)
    failure_stage: str | None = Field(default=None, max_length=120)
    failure_summary: str | None = Field(default=None, max_length=500)
    fingerprint: str | None = Field(default=None, max_length=64)
    action_fingerprint: str | None = Field(default=None, max_length=64)
    recovery: Literal["continue", "revise_map", "alternate_source", "terminal"] = (
        "continue"
    )
    observed_at: str | None = Field(default=None, max_length=64)


###############################################################################
TaskStatus = Literal[
    "pending",
    "in_progress",
    "completed",
    "failed",
    "blocked",
    "cancelled",
    "superseded",
]


###############################################################################
class AgentTask(BaseModel):
    """One lightweight, run-scoped obligation.

    Tasks are operational state, not a second planner.  The native loop owns
    their status and the model receives only the bounded projection embedded
    in :class:`AgentTaskState`.
    """

    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1, max_length=500)
    status: TaskStatus = "pending"
    parent_task_id: str | None = Field(default=None, max_length=160)
    dependencies: list[str] = Field(default_factory=list, max_length=16)
    requirement_name: str | None = Field(default=None, max_length=120)
    target_id: str | None = Field(default=None, max_length=160)
    result: dict[str, object] | None = None
    failure_code: str | None = Field(default=None, max_length=120)

    # -------------------------------------------------------------------------
    @property
    def id(self) -> str:
        """Compatibility/readability alias for consumers that call it ``id``."""

        return self.task_id


###############################################################################
class AgentTaskState(BaseModel):
    """Typed projection of the run-scoped task ledger.

    The durable ``AgentRunState.task_state`` field intentionally remains a
    JSON object for checkpoint compatibility with older native runs.  This
    model is the schema and normalization boundary for that object.
    """

    # Conversation-state fields may coexist in the legacy JSON projection;
    # they are deliberately ignored by this task-ledger view.
    model_config = ConfigDict(extra="ignore")

    root_task_id: str = Field(min_length=1, max_length=160)
    active_task_id: str | None = Field(default=None, max_length=160)
    status: TaskStatus = "pending"
    current_iteration: int = Field(default=0, ge=0)
    max_iterations: int = Field(default=1, ge=1, le=100)
    tasks: list[AgentTask] = Field(
        default_factory=lambda: list[AgentTask](), max_length=32
    )
    completion_requirements: list[CompletionRequirement] = Field(
        default_factory=lambda: list[CompletionRequirement](), max_length=16
    )

    # -------------------------------------------------------------------------
    @classmethod
    def create(
        cls,
        *,
        run_id: str,
        description: str,
        max_iterations: int,
        requirements: list[str] | None = None,
        target_ids: list[str] | None = None,
        compound: bool = False,
    ) -> "AgentTaskState":
        """Create a deterministic root task and optional child obligations."""

        root_task_id = f"task-root-{_safe_task_id(run_id)}"
        root = AgentTask(
            task_id=root_task_id,
            description=description[:500],
            status="in_progress",
        )
        names = list(dict.fromkeys(str(item).strip() for item in requirements or [] if str(item).strip()))
        targets = list(dict.fromkeys(str(item).strip() for item in target_ids or [] if str(item).strip()))
        children: list[AgentTask] = []
        if compound:
            for name in names:
                children.append(
                    AgentTask(
                        task_id=f"{root_task_id}:requirement:{_safe_task_id(name)}",
                        description=f"Satisfy {name.replace('_', ' ')}.",
                        parent_task_id=root_task_id,
                        requirement_name=name,
                    )
                )
            for target in targets:
                children.append(
                    AgentTask(
                        task_id=f"{root_task_id}:target:{_safe_task_id(target)}",
                        description=f"Complete the request for {target}.",
                        parent_task_id=root_task_id,
                        target_id=target,
                    )
                )
        return cls(
            root_task_id=root_task_id,
            active_task_id=root_task_id,
            status="in_progress",
            current_iteration=0,
            max_iterations=max(1, min(100, int(max_iterations))),
            tasks=[root, *children][:32],
            completion_requirements=[CompletionRequirement(name=name) for name in names],
        )

    # -------------------------------------------------------------------------
    @classmethod
    def from_payload(
        cls,
        payload: object,
        *,
        run_id: str = "unknown",
        description: str = "Native agent request",
        max_iterations: int = 1,
    ) -> "AgentTaskState":
        """Normalize a legacy or partially populated task JSON object."""

        payload_object = (
            cast(dict[str, object], payload) if isinstance(payload, dict) else {}
        )
        if payload_object.get("root_task_id"):
            try:
                return cls.model_validate(payload_object)
            except Exception:
                # A malformed persisted projection must not make a run
                # unrecoverable; rebuild the bounded root ledger below.
                pass
        return cls.create(
            run_id=run_id,
            description=description,
            max_iterations=max_iterations,
        )

    # -------------------------------------------------------------------------
    def to_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude_none=True)


###############################################################################
def _safe_task_id(value: str) -> str:
    normalized = "-".join(str(value).strip().casefold().split())
    safe = "".join(char if char.isalnum() or char in "-_" else "-" for char in normalized)
    return (safe.strip("-") or "unknown")[:96]

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
class LoopDecision(StrEnum):
    """Authoritative outcome of one route/tool/render control observation."""

    CONTINUE = "continue"
    REQUEST_CLARIFICATION = "request_clarification"
    AWAIT_RENDER = "await_render"
    FINALIZE = "finalize"
    COMPLETE = "complete"
    FAIL = "fail"
    CANCEL = "cancel"
    SUPERSEDE = "supersede"

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
    render_observations: list[RenderObservation] = Field(
        default_factory=lambda: list[RenderObservation](), max_length=8
    )
    render_attempts: int = Field(default=0, ge=0, le=32)
    render_verified: bool = False
    render_retry_exhausted: bool = False
    prepared_map_action_fingerprint: str | None = Field(
        default=None, max_length=64
    )
    failed_render_fingerprints: dict[str, int] = Field(
        default_factory=lambda: dict[str, int]()
    )
    no_progress_corrections: int = Field(default=0, ge=0, le=8)
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
    # Iterations are one-based once the first model decision starts.  Keeping
    # the explicit alias makes checkpoints and diagnostics readable while
    # retaining ``current_iteration`` as the canonical field.
    current_iteration: int = Field(default=0, ge=0)
    iteration: int = Field(default=0, ge=0)
    max_iterations: int = Field(default=12, ge=1, le=100)
    finalization_attempted: bool = False
    iteration_trace: list[dict[str, object]] = Field(
        default_factory=lambda: list[dict[str, object]]()
    )
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

    # -------------------------------------------------------------------------
    def typed_task_state(self) -> AgentTaskState:
        """Return the validated task ledger for this run.

        Older checkpoints and callers may still supply arbitrary task JSON;
        the normalization helper gives them a safe root task without mutating
        the canonical state until the loop explicitly persists it.
        """

        return AgentTaskState.from_payload(
            self.task_state,
            run_id=self.run_id or self.request_id,
            description=self.user_message,
            max_iterations=self.max_iterations,
        )

    # -------------------------------------------------------------------------
    def set_typed_task_state(self, value: AgentTaskState) -> None:
        """Persist a typed ledger as the checkpoint-compatible JSON object."""

        self.task_state = value.to_payload()

    # -------------------------------------------------------------------------
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
        payload["render_observations"] = [
            item.model_dump(mode="json") for item in self.render_observations[-8:]
        ]
        payload["failed_render_fingerprints"] = dict(
            list(self.failed_render_fingerprints.items())[-32:]
        )
        return payload

    # -------------------------------------------------------------------------
    @classmethod
    def from_checkpoint(cls, payload: dict[str, Any]) -> "AgentRunState":
        """Restore one validated native run checkpoint."""

        state = cls.model_validate(payload)
        # Checkpoints written by the earlier native harness used ``iteration``
        # (and the task ledger) as the progress counter.  Reconcile all three
        # representations so a resumed run cannot silently restart at one.
        task_iteration = 0
        try:
            task_iteration = state.typed_task_state().current_iteration
        except Exception:
            task_iteration = 0
        cumulative = max(
            int(state.current_iteration), int(state.iteration), int(task_iteration)
        )
        state.current_iteration = cumulative
        state.iteration = cumulative
        return state


###############################################################################
def _checkpoint_tool_result(value: ToolResult) -> dict[str, Any]:
    """Keep model-facing result data without embedding raw provider payloads."""

    observation = ModelObservation.from_tool_result(value, max_chars=4096)
    return value.model_copy(update={"data": observation.result}, deep=True).model_dump(
        mode="json"
    )
