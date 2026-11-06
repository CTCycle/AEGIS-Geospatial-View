"""Typed routing, goal, and run-state contracts for the native agent."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from server.common.identifiers import location_ref_matches, normalize_target_key, parse_coordinate_pair
from server.common.typing import json_object
from server.contracts.geospatial import MapSession
from server.domain.agent.capability_domains import CapabilityDomain
from server.domain.agent.decision import ResolvedLocation
from server.domain.agent.tool_result import ModelObservation, ToolResult
from server.domain.agent.vision_policy import VisionState

###############################################################################
class AgentAnalysisIntent(BaseModel):
    """Provider-neutral analysis selected from the user's objective."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["rank", "hotspot", "threshold"]
    metric: str = Field(min_length=1, max_length=120)
    order: str = Field(default="descending", max_length=40)
    top_k: int = Field(default=5, ge=1, le=25)

# "identification": name or describe a place, e.g. what place coordinates are.
ObligationKind = Literal["location", "data", "analysis", "presentation", "identification"]

###############################################################################
class RouteObligation(BaseModel):
    # Described once on CapabilityRoute.obligations to keep the schema small.

    model_config = ConfigDict(extra="forbid")

    kind: ObligationKind
    target_refs: list[str] = Field(default_factory=lambda: list[str](), max_length=16)
    variable: str | None = Field(default=None, min_length=1, max_length=120)
    required: bool = True

###############################################################################
class CapabilityRoute(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary_domain: CapabilityDomain
    secondary_domains: list[CapabilityDomain] = Field(
        default_factory=lambda: list[CapabilityDomain](), max_length=3
    )
    task_mode: Literal["answer", "execute", "clarify"]
    presentation: Literal["text", "map", "both"]
    # Models often omit this field; the router upgrades "none" to "target" when
    # a new map or a semantic target needs a place, so the default is safe.
    location_mode: Literal["none", "target", "search_area"] = "none"
    analysis: AgentAnalysisIntent | None = None
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
    # Compound requests ("Rome today vs Milan tomorrow") give a target its own
    # scope; an unset field falls back to the route-level scope above.
    target_requirements: list["TargetRequirement"] = Field(
        default_factory=lambda: list[TargetRequirement](), max_length=16
    )
    filters: dict[str, Any] = Field(default_factory=lambda: dict[str, Any]())
    obligations: list[RouteObligation] = Field(
        default_factory=lambda: list[RouteObligation](),
        max_length=16,
        description=(
            "Every explicit part of the latest request, so none is dropped: kind "
            "location (a place), data (values), analysis (comparison/ranking), "
            "presentation (shown on the map) or identification (name a place)."
        ),
    )

    # -------------------------------------------------------------------------
    @model_validator(mode="after")
    def _requirements_name_route_targets(self) -> "CapabilityRoute":
        known = {normalize_target_key(ref) for ref in self.target_refs}
        seen: set[str] = set()
        for requirement in self.target_requirements:
            key = normalize_target_key(requirement.target_ref)
            if key not in known:
                raise ValueError(
                    f"target_requirements names '{requirement.target_ref}', which is not in target_refs"
                )
            if key in seen:
                raise ValueError(f"target_requirements repeats '{requirement.target_ref}'")
            seen.add(key)
        return self

###############################################################################
class TargetRequirement(BaseModel):
    """Scope that applies to one target only; unset fields use the route's."""

    model_config = ConfigDict(extra="forbid")

    target_ref: str = Field(min_length=1, max_length=160)
    temporal_scope: "AgentTemporalScope | None" = None
    spatial_scope: "AgentSpatialScope | None" = None

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
class RequestObligation(BaseModel):
    """One server-normalized part of the request the run must honour.

    Derived from the validated route (targets, data needs, analysis and
    presentation) plus the parts the routing model declared, so tasks,
    coverage checks and completion read the same obligations.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=200)
    kind: ObligationKind
    target_ids: list[str] = Field(default_factory=lambda: list[str](), max_length=16)
    variable: str | None = Field(default=None, max_length=120)
    temporal_scope: AgentTemporalScope | None = None
    required: bool = True

###############################################################################
class AgentGoal(BaseModel):
    """Server-owned goal details derived from a validated native route."""

    model_config = ConfigDict(extra="forbid")

    goal: str
    task_mode: Literal["answer", "execute", "clarify"]
    presentation: Literal["text", "map", "both"]
    operation: str
    location_mode: Literal["none", "target", "search_area"]
    analysis: AgentAnalysisIntent | None = None
    target_ids: list[str] = Field(default_factory=lambda: list[str](), max_length=16)
    temporal_scope: dict[str, object] = Field(
        default_factory=lambda: dict[str, object]()
    )
    spatial_scope: list[dict[str, object]] = Field(
        default_factory=lambda: list[dict[str, object]](), max_length=16
    )
    # Per-target scopes with the route-level fallback already applied; empty
    # for single-scope requests.
    target_requirements: list[TargetRequirement] = Field(
        default_factory=lambda: list[TargetRequirement](), max_length=16
    )
    filters: dict[str, object] = Field(
        default_factory=lambda: dict[str, object]()
    )
    obligations: list[RequestObligation] = Field(
        default_factory=lambda: list[RequestObligation](), max_length=32
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
    # Requested analytical components; each needs validated evidence from a
    # capability whose manifest covers it (one source may cover several).
    data_obligations: list[str] = Field(default_factory=lambda: list[str](), max_length=4)
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
    "evidence_analysis",
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
    # Share of the prepared result extent inside the browser viewport; below 1
    # the user sees only part of the result (for example after a minzoom bump).
    results_in_viewport: float | None = Field(default=None, ge=0.0, le=1.0)
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
    obligation_id: str | None = Field(default=None, max_length=200)
    result: dict[str, object] | None = None
    failure_code: str | None = Field(default=None, max_length=120)

###############################################################################
class AgentTaskState(BaseModel):
    """Typed projection of the run-scoped task ledger.

    The durable ``AgentRunState.task_state`` JSON object carries both the
    conversation-state projection and this task ledger, so the typed view
    deliberately ignores the conversation keys and claims its own namespace.
    """

    model_config = ConfigDict(extra="ignore")

    root_task_id: str = Field(min_length=1, max_length=160)
    active_task_id: str | None = Field(default=None, max_length=160)
    status: TaskStatus = "pending"
    current_iteration: int = Field(default=0, ge=0)
    max_iterations: int = Field(default=1, ge=1, le=1000)
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
        obligations: list[RequestObligation] | None = None,
        compound: bool = False,
    ) -> "AgentTaskState":
        """Create a deterministic root task and its child obligations.

        Children come from the completion requirements and the goal's request
        obligations, so the ledger tracks the same parts of the request that
        coverage and completion checks read.
        """

        root_task_id = f"task-root-{_safe_task_id(run_id)}"
        root = AgentTask(
            task_id=root_task_id,
            description=description[:500],
            status="in_progress",
        )
        names = list(dict.fromkeys(str(item).strip() for item in requirements or [] if str(item).strip()))
        children: list[AgentTask] = []
        if compound:
            # A requirement an obligation already tracks gets no second task.
            tracked = {
                "location_resolved" if item.kind == "location" else obligation_requirement(item.kind, names)
                for item in obligations or []
                if item.required
            }
            if "location_resolved" in tracked:
                tracked.add("search_area_bound")
            for name in names:
                if name in tracked:
                    continue
                children.append(
                    AgentTask(
                        task_id=f"{root_task_id}:requirement:{_safe_task_id(name)}",
                        description=f"Satisfy {name.replace('_', ' ')}.",
                        parent_task_id=root_task_id,
                        requirement_name=name,
                    )
                )
            for obligation in obligations or []:
                if not obligation.required:
                    continue
                children.append(
                    AgentTask(
                        task_id=f"{root_task_id}:{_safe_task_id(obligation.id)}",
                        description=obligation.kind,
                        parent_task_id=root_task_id,
                        obligation_id=obligation.id,
                        # A location obligation is tracked by its place; every
                        # other kind by the requirement that satisfies it.
                        requirement_name=(
                            None
                            if obligation.kind == "location"
                            else obligation_requirement(obligation.kind, names)
                        ),
                        target_id=(
                            obligation.target_ids[0]
                            if obligation.kind == "location" and obligation.target_ids
                            else None
                        ),
                    )
                )
        return cls(
            root_task_id=root_task_id,
            active_task_id=root_task_id,
            status="in_progress",
            current_iteration=0,
            max_iterations=max(1, min(1000, int(max_iterations))),
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
        """Normalize a task JSON object into the typed ledger.

        Runs whose context projection has not initialized the ledger yet get a
        deterministic root task; a malformed persisted projection raises so
        corruption is surfaced instead of silently restarting progress.
        """

        payload_object = (
            cast(dict[str, object], payload) if isinstance(payload, dict) else {}
        )
        if payload_object.get("root_task_id"):
            return cls.model_validate(payload_object)
        return cls.create(
            run_id=run_id,
            description=description,
            max_iterations=max_iterations,
        )

    # -------------------------------------------------------------------------
    def to_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude_none=True)

###############################################################################
ConversationTaskStatus = Literal["in_progress", "completed", "failed"]

###############################################################################
class ConversationTask(BaseModel):
    """One request obligation's verified outcome, kept across turns.

    Written only from a run's validated completion summary at the commit, so
    a later turn can reuse places, evidence and the shown map without
    trusting what a model said it did.  ``task_id`` is the obligation id, so
    a later run that redoes the same part of a request replaces the entry.
    """

    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=300)
    kind: ObligationKind
    status: ConversationTaskStatus
    dependencies: list[str] = Field(default_factory=lambda: list[str](), max_length=16)
    target_ids: list[str] = Field(default_factory=lambda: list[str](), max_length=16)
    capability_id: str | None = Field(default=None, max_length=160)
    variable: str | None = Field(default=None, max_length=120)
    temporal_scope: AgentTemporalScope | None = None
    filters: dict[str, object] = Field(default_factory=lambda: dict[str, object]())
    evidence_refs: list[str] = Field(default_factory=lambda: list[str](), max_length=8)
    # Content fingerprint of the map a presentation task prepared or showed.
    map_revision: str | None = Field(default=None, max_length=64)
    source_request_id: str = Field(min_length=1, max_length=160)
    completed_at: datetime | None = None

###############################################################################
# Completion requirements that satisfy each obligation kind, most specific
# first.  An obligation with none of them in the contract is unrouted.
OBLIGATION_REQUIREMENTS: dict[ObligationKind, tuple[str, ...]] = {
    "location": ("location_resolved", "search_area_bound"),
    "data": (
        "required_data_retrieved",
        "evidence_inspected",
        "measurement_computed",
        "capabilities_discovered",
    ),
    "analysis": (
        "result_locations_derived",
        "measurement_computed",
        "required_data_retrieved",
        "evidence_inspected",
    ),
    "presentation": ("map_candidate_prepared",),
    # The place is named by its resolution (a reverse geocode for coordinates).
    "identification": ("location_resolved", "search_area_bound"),
}

###############################################################################
def obligation_requirement(kind: ObligationKind, requirements: list[str]) -> str | None:
    """Return the completion requirement that satisfies an obligation kind."""

    return next(
        (name for name in OBLIGATION_REQUIREMENTS[kind] if name in requirements), None
    )

###############################################################################
def same_target(left: str, right: str) -> bool:
    """Whether two target spellings name the same place."""

    return (
        normalize_target_key(left) == normalize_target_key(right)
        or location_ref_matches(left, right, None)
        or location_ref_matches(right, left, None)
    )

###############################################################################
def places_named_in(message: str, locations: dict[str, ResolvedLocation]) -> list[tuple[str, str]]:
    """Return (key, name) of each resolved place the message names again.

    A place counts as named when its leading label part ("Tokyo" of "Tokyo,
    Japan") appears as whole words in the message.
    """

    text = f" {normalize_target_key(message)} "
    named: list[tuple[str, str]] = []
    for key, location in locations.items():
        name = (location.label or str(key)).split(",")[0].strip()
        normalized = normalize_target_key(name)
        if len(normalized) >= 3 and f" {normalized} " in text:
            named.append((str(key), name))
    return named

###############################################################################
def names_data_subject(query: str, route: CapabilityRoute) -> bool:
    """True when a place query only repeats what the request asks about.

    The data subject and capability terms of a route (a variable, an analysis
    metric, a capability query) describe the data, not a place.  A query that
    adds anything to such a term (for example a place name) is not the subject.
    """

    def tokens(value: str) -> set[str]:
        return {
            word[:-1] if len(word) > 3 and word.endswith("s") else word
            for word in normalize_target_key(value).split()
        }

    asked = tokens(query)
    terms = [
        *(item.variable for item in route.obligations if item.kind in {"data", "analysis"}),
        route.analysis.metric if route.analysis else None,
        *route.capability_queries,
    ]
    return bool(asked) and any(asked == tokens(term) for term in terms if term)

###############################################################################
def derive_request_obligations(
    route: CapabilityRoute,
    *,
    target_ids: list[str],
    target_requirements: list[TargetRequirement],
    requirements: list[str],
    data_variables: list[str],
) -> list[RequestObligation]:
    """Normalize the validated route and its declared parts into obligations.

    Places, provider data, analysis and map presentation come from the route
    and its completion requirements; a part the routing model declared that
    none of them expresses is kept as its own obligation, so the consistency
    check can see that the route dropped it.
    """

    route_scope = route.temporal_scope if route.temporal_scope != AgentTemporalScope() else None

    def scope_for(target: str | None) -> AgentTemporalScope | None:
        requirement = next(
            (
                item
                for item in target_requirements
                if target is not None and same_target(item.target_ref, target)
            ),
            None,
        )
        if requirement is not None and requirement.temporal_scope is not None:
            return requirement.temporal_scope
        return route_scope

    obligations: list[RequestObligation] = []
    # A map-state route edits the current map: its targets name layers and
    # styles on it, not places to locate.
    if route.location_mode != "none" and route.primary_domain is not CapabilityDomain.MAP_STATE:
        obligations.extend(
            RequestObligation(
                id=f"location:{_safe_task_id(target)}",
                kind="location",
                target_ids=[target],
                temporal_scope=scope_for(target),
            )
            for target in target_ids
        )
    variables: list[str | None] = [
        *(data_variables or route.capability_queries[:1])
    ] or [None]
    # Data and its map are per requested place; spatial-scope anchors are not.
    places = list(dict.fromkeys(ref.strip() for ref in route.target_refs if ref.strip()))
    if "required_data_retrieved" in requirements:
        data_targets: list[str | None] = [*places] or [None]
        obligations.extend(
            RequestObligation(
                id=":".join(
                    ["data", *(_safe_task_id(part) for part in (target, variable) if part)]
                ),
                kind="data",
                target_ids=[target] if target else [],
                variable=variable,
                temporal_scope=scope_for(target),
            )
            for target in data_targets
            for variable in variables
        )
    if route.analysis is not None or "measurement_computed" in requirements:
        obligations.append(
            RequestObligation(
                id=f"analysis:{route.analysis.kind if route.analysis else 'measurement'}",
                kind="analysis",
                target_ids=list(target_ids),
                variable=route.analysis.metric if route.analysis else None,
            )
        )
    if route.presentation in {"text", "both"} and route.location_mode != "none":
        # A text answer about bare coordinates must say where they are.
        obligations.extend(
            RequestObligation(
                id=f"identification:{_safe_task_id(target)}",
                kind="identification",
                target_ids=[target],
            )
            for target in target_ids
            if parse_coordinate_pair(target) is not None
        )
    if route.presentation in {"map", "both"}:
        obligations.append(
            RequestObligation(
                id="presentation:map",
                kind="presentation",
                target_ids=places,
                variable=(
                    route.analysis.metric
                    if route.analysis is not None
                    else variables[0] if len(variables) == 1 else None
                ),
            )
        )
    for declared in route.obligations:
        targets = [
            next((known for known in target_ids if same_target(ref, known)), ref.strip())
            for ref in declared.target_refs
            if ref.strip()
        ]
        if any(
            existing.kind == declared.kind
            and all(
                any(same_target(target, other) for other in existing.target_ids)
                for target in targets
            )
            for existing in obligations
        ):
            continue
        base = ":".join([declared.kind, *(_safe_task_id(t) for t in targets)] or [declared.kind])
        identifier = base
        suffix = 2
        while any(item.id == identifier for item in obligations):
            identifier = f"{base}:{suffix}"
            suffix += 1
        obligations.append(
            RequestObligation(
                id=identifier[:200],
                kind=declared.kind,
                target_ids=targets[:16],
                variable=declared.variable,
                temporal_scope=next((scope_for(t) for t in targets), route_scope),
                required=declared.required,
            )
        )
    return obligations[:32]

###############################################################################
def unrouted_obligations(
    goal: AgentGoal, requirements: list[str]
) -> tuple[str, list[RequestObligation]] | None:
    """Name required obligations the validated route cannot satisfy.

    Each required obligation must map to a route target, a completion
    requirement, or the route's presentation/analysis.  Returns a specific
    reason code with the offending obligations, or None when consistent.
    """

    required = [item for item in goal.obligations if item.required]
    missing_targets = [
        item
        for item in required
        if any(
            not any(same_target(target, known) for known in goal.target_ids)
            for target in item.target_ids
        )
    ]
    if missing_targets:
        return "obligation_target_missing", missing_targets

    def routed(item: RequestObligation) -> bool:
        if item.kind == "location":
            return True
        if item.kind == "presentation":
            return goal.presentation in {"map", "both"}
        if item.kind == "analysis" and goal.analysis is not None:
            return True
        return obligation_requirement(item.kind, requirements) is not None

    unrouted = [item for item in required if not routed(item)]
    if not unrouted:
        return None
    compound = {"analysis", "presentation"}
    unrouted_kinds = {item.kind for item in unrouted}
    if compound <= {item.kind for item in required} and len(unrouted_kinds & compound) == 1:
        # "Compare ... and show it on the map" kept only one of its halves.
        return "compound_obligation_dropped", unrouted
    return f"{unrouted[0].kind}_obligation_unrouted", unrouted

###############################################################################
def dropped_obligations(
    previous: list[RequestObligation], current: list[RequestObligation]
) -> list[RequestObligation]:
    """Return prior required obligations a revised goal no longer carries.

    A location, data or identification obligation is kept only when the
    revision still names each of its places; analysis and presentation only
    need the same kind.
    """

    dropped: list[RequestObligation] = []
    for item in previous:
        if not item.required:
            continue
        same_kind = [other for other in current if other.required and other.kind == item.kind]
        if not same_kind:
            dropped.append(item)
            continue
        if item.kind in {"location", "data", "identification"} and not all(
            any(same_target(target, other_target) for other in same_kind for other_target in other.target_ids)
            for target in item.target_ids
        ):
            dropped.append(item)
    return dropped

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
    execution_policy: dict[str, Any] = Field(default_factory=dict)
    route: CapabilityRoute | None = None
    capability_ids: list[str] = Field(default_factory=lambda: list[str]())
    excluded_capability_ids: list[str] = Field(
        default_factory=lambda: list[str](), max_length=32
    )
    location_refs: dict[str, ResolvedLocation] = Field(
        default_factory=lambda: dict[str, ResolvedLocation]()
    )
    evidence_refs: list[str] = Field(default_factory=lambda: list[str]())
    # Conversation ledger tasks from earlier turns; narrowed to the ones
    # compatible with this run's goal once the goal is compiled.
    prior_tasks: list[ConversationTask] = Field(
        default_factory=lambda: list[ConversationTask](), max_length=32
    )
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
    # Transient provider failures per "capability|target": one retry is allowed.
    transient_failures: dict[str, int] = Field(default_factory=lambda: dict[str, int]())
    # Targets whose data source kept failing, mapped to the capability that failed.
    failed_data_targets: dict[str, str] = Field(default_factory=lambda: dict[str, str]())
    route_corrections: int = Field(default=0, ge=0)
    # At most one revision per run: old route, new route and the evidence that
    # showed the first interpretation could not be executed.
    route_revisions: list[dict[str, object]] = Field(
        default_factory=lambda: list[dict[str, object]](), max_length=1
    )
    # How the route was chosen: the routing model, the deterministic fast
    # path, or the deterministic fallback after routing failed.
    route_source: Literal["model", "fast", "fallback"] = "model"
    validation_corrections: int = Field(default=0, ge=0)
    # Iterations are one-based once the first model decision starts.
    current_iteration: int = Field(default=0, ge=0)
    max_iterations: int = Field(default=40, ge=1, le=1000)
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
    exposure_trace: list[dict[str, Any]] = Field(
        default_factory=lambda: list[dict[str, Any]]()
    )
    discovery_attempts: int = Field(default=0, ge=0)
    # Server discovery refreshes already run for a location set; an
    # unchanged set would return the same shortlist.
    discovery_refresh_keys: list[str] = Field(
        default_factory=lambda: list[str](), max_length=16
    )
    # Progress ledger: a digest of what the run has established, and how
    # many consecutive tool steps left it unchanged.
    progress_signatures: list[str] = Field(
        default_factory=lambda: list[str](), max_length=64
    )
    unproductive_steps: int = Field(default=0, ge=0)
    stuck_notices: int = Field(default=0, ge=0)
    # The server mapped the run's evidence once after the model stalled.
    evidence_map_recovered: bool = False
    budget_snapshot: dict[str, object] = Field(
        default_factory=lambda: dict[str, object]()
    )
    vision_state: VisionState | None = None
    termination_reason: str | None = None

    # -------------------------------------------------------------------------
    def typed_task_state(self) -> AgentTaskState:
        """Return the validated task ledger for this run.

        A run whose context projection has not initialized the ledger yet
        receives a safe root task without mutating the canonical state until
        the loop explicitly persists it.
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
        payload["provider_continuation"] = list(self.provider_continuation)
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

        return cls.model_validate(payload)

###############################################################################
def _checkpoint_tool_result(value: ToolResult) -> dict[str, Any]:
    """Keep model-facing result data without embedding raw provider payloads."""

    observation = ModelObservation.from_tool_result(value, max_chars=4096)
    data = json_object(observation.result)
    # Target coverage is durable execution state. Model projections (notably
    # weather tables) may omit query fields, but render/resume must retain the
    # binding without retaining provider arguments or raw payloads.
    location_ref = json_object(json_object(value.data).get("query")).get("location_ref")
    if value.tool_name == "execute_geospatial_capability" and isinstance(location_ref, str):
        data = {**data, "query": {"location_ref": location_ref}}
    return value.model_copy(update={"data": data or observation.result}, deep=True).model_dump(
        mode="json"
    )
