"""Small, provider-neutral contracts for the AEGIS agent runtime.

The runtime deliberately keeps orchestration in ordinary application code.  These
models are the durable boundary between a conversation/thread, an execution
run, and the geospatial evidence produced by tools.  They are intentionally
independent from any LLM SDK so they can also be used by scripted benchmark
models and deterministic failure tests.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field

AgentTaskStatus = Literal[
    "pending",
    "in_progress",
    "completed",
    "failed",
    "blocked",
    "skipped",
    "superseded",
]
CompletionReason = Literal[
    "completed",
    "partial",
    "clarification_required",
    "required_task_failed",
    "budget_exhausted",
    "no_progress",
    "cancelled",
    "superseded_by_steering",
]

###############################################################################
class AgentGoal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    text: str
    status: Literal["active", "completed", "partial", "superseded"] = "active"
    revision: int = Field(default=0, ge=0)

###############################################################################
class GeographicScope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bbox: list[float] | None = None
    radius_m: float | None = Field(default=None, gt=0)
    geometry_ref: str | None = None
    exclusions: list[dict[str, Any]] = Field(default_factory=lambda: list[dict[str, Any]]())
    crs: str = "EPSG:4326"

###############################################################################
class GeospatialWorkingState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resolved_locations: list[dict[str, Any]] = Field(default_factory=lambda: list[dict[str, Any]]())
    geographic_scope: GeographicScope = Field(default_factory=GeographicScope)
    candidate_place_refs: list[str] = Field(default_factory=list)
    selected_place_ids: list[str] = Field(default_factory=list)
    data_source_refs: list[str] = Field(default_factory=list)
    layer_refs: list[str] = Field(default_factory=list)
    feature_refs: list[str] = Field(default_factory=list)
    temporal_constraints: dict[str, Any] = Field(default_factory=dict)
    renderable_refs: list[str] = Field(default_factory=list)

###############################################################################
class AgentTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    description: str
    kind: str = "research"
    status: AgentTaskStatus = "pending"
    depends_on: list[str] = Field(default_factory=list)
    required: bool = True
    input_refs: list[str] = Field(default_factory=list)
    output_refs: list[str] = Field(default_factory=list)
    attempt_count: int = Field(default=0, ge=0)
    last_failure: dict[str, Any] | None = None
    scope_revision: int = Field(default=0, ge=0)

###############################################################################
class AgentThreadState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[3] = 3
    conversation_id: str
    revision: int = Field(default=0, ge=0)
    active_task_id: str | None = None
    goal: AgentGoal | None = None
    tasks: list[AgentTask] = Field(default_factory=lambda: list[AgentTask]())
    geospatial_state: GeospatialWorkingState = Field(default_factory=GeospatialWorkingState)
    evidence_refs: list[str] = Field(default_factory=list)
    active_map_session: dict[str, Any] | None = None
    assumptions: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    conversation_summary: dict[str, Any] | None = None

###############################################################################
class AgentBudgets(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_calls: int
    tool_calls: int
    state_transitions: int
    plan_revisions: int = 0
    wall_clock_seconds: float

###############################################################################
class AgentRunState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    run_version: int = Field(default=1, ge=1)
    phase: str = "planning"
    active_task_id: str | None = None
    plan_revision: int = Field(default=0, ge=0)
    budgets: AgentBudgets
    model_calls: int = Field(default=0, ge=0)
    tool_calls: int = Field(default=0, ge=0)
    state_transitions: int = Field(default=0, ge=0)
    completed_call_fingerprints: list[str] = Field(default_factory=list)
    consecutive_no_progress_steps: int = Field(default=0, ge=0)
    completion_reason: CompletionReason | None = None

###############################################################################
class ToolCapabilityProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    category: str
    capabilities: list[str] = Field(default_factory=list)
    input_types: list[str] = Field(default_factory=list)
    output_types: list[str] = Field(default_factory=list)
    geographic_coverage: list[str] = Field(default_factory=list)
    temporal_coverage: list[str] = Field(default_factory=list)
    prerequisites: list[str] = Field(default_factory=list)
    supports_rendering: bool = False
    expected_latency_seconds: float = Field(default=1.0, ge=0)
    healthy: bool = True

###############################################################################
class RuntimeValidationError(ValueError):
    """Raised when an application-owned runtime invariant is violated."""

###############################################################################
def validate_task_graph(tasks: list[AgentTask]) -> None:
    """Validate unique task IDs, existing dependencies, and acyclicity."""

    by_id = {task.id: task for task in tasks}
    if len(by_id) != len(tasks):
        raise RuntimeValidationError("Task IDs must be unique.")
    for task in tasks:
        if task.id in task.depends_on:
            raise RuntimeValidationError(f"Task '{task.id}' cannot depend on itself.")
        missing = [dependency for dependency in task.depends_on if dependency not in by_id]
        if missing:
            raise RuntimeValidationError(
                f"Task '{task.id}' has missing dependencies: {', '.join(missing)}."
            )
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(task_id: str) -> None:
        if task_id in visiting:
            raise RuntimeValidationError("Task plan contains a dependency cycle.")
        if task_id in visited:
            return
        visiting.add(task_id)
        for dependency in by_id[task_id].depends_on:
            visit(dependency)
        visiting.remove(task_id)
        visited.add(task_id)

    for task in tasks:
        visit(task.id)

###############################################################################
def runnable_tasks(tasks: list[AgentTask]) -> list[AgentTask]:
    """Return pending tasks whose required dependencies completed successfully."""

    by_id = {task.id: task for task in tasks}
    return [
        task
        for task in tasks
        if task.status == "pending"
        and all(by_id[dependency].status == "completed" for dependency in task.depends_on)
    ]

###############################################################################
def block_tasks_with_failed_dependencies(tasks: list[AgentTask]) -> int:
    """Mark dependent tasks blocked; failed work is never treated as success."""

    by_id = {task.id: task for task in tasks}
    changed = 0
    for task in tasks:
        if task.status != "pending":
            continue
        if any(
            by_id[dependency].status in {"failed", "blocked", "superseded"}
            for dependency in task.depends_on
        ):
            task.status = "blocked"
            task.last_failure = {
                "code": "dependency_failed",
                "message": "A required predecessor did not complete successfully.",
            }
            changed += 1
    return changed

###############################################################################
def canonical_call_fingerprint(tool_name: str, arguments: dict[str, Any]) -> str:
    payload = json.dumps(
        {"tool": tool_name, "arguments": arguments},
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

###############################################################################
def select_tools(
    profiles: list[ToolCapabilityProfile],
    *,
    category: str | None = None,
    capabilities: set[str] | None = None,
    require_rendering: bool = False,
) -> list[ToolCapabilityProfile]:
    """Deterministically filter capabilities; no extra model selector is used."""

    wanted = capabilities or set()
    return [
        profile
        for profile in profiles
        if profile.healthy
        and (category is None or profile.category == category)
        and wanted.issubset(set(profile.capabilities))
        and (not require_rendering or profile.supports_rendering)
    ]

###############################################################################
def state_fingerprint(state: AgentThreadState) -> str:
    payload = state.model_dump(mode="json", exclude={"conversation_summary"})
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()

###############################################################################
def compact_task_context(task_state: dict[str, Any], *, completed_limit: int = 6) -> dict[str, Any]:
    """Keep active dependencies and a small completed window in model context."""

    raw_tasks: Any = task_state.get("tasks")
    if not isinstance(raw_tasks, list):
        return task_state
    active: list[dict[str, Any]] = []
    completed: list[dict[str, Any]] = []
    for raw_value in cast(list[Any], raw_tasks):
        if not isinstance(raw_value, dict):
            continue
        raw = cast(dict[str, Any], raw_value)
        status = raw.get("status")
        item = {
            key: raw.get(key)
            for key in (
                "id",
                "description",
                "kind",
                "status",
                "depends_on",
                "required",
                "input_refs",
                "output_refs",
                "attempt_count",
                "last_failure",
                "scope_revision",
            )
            if key in raw
        }
        if status == "completed":
            completed.append(item)
        else:
            active.append(item)
    compact = dict(task_state)
    compact["tasks"] = [*active, *completed[-completed_limit:]]
    compact["completed_tasks_omitted"] = max(0, len(completed) - completed_limit)
    return compact

###############################################################################
def evaluate_completion(state: AgentThreadState) -> CompletionReason | None:
    """Return a completion reason only when required tasks are terminal."""

    if state.unresolved_questions:
        return "clarification_required"
    required = [task for task in state.tasks if task.required]
    if not required:
        return "completed" if state.goal and state.goal.status == "completed" else None
    if any(task.status in {"pending", "in_progress"} for task in required):
        return None
    if any(task.status in {"failed", "blocked"} for task in required):
        return "required_task_failed"
    if any(task.status == "superseded" for task in required):
        return "partial"
    return "completed"

###############################################################################
@dataclass(frozen=True)
class ScopeInvalidation:
    invalidated_evidence_refs: tuple[str, ...]
    retained_evidence_refs: tuple[str, ...]

###############################################################################
def invalidate_scope_evidence(
    state: AgentThreadState,
    *,
    invalidated_refs: set[str],
    new_scope: GeographicScope | None = None,
) -> ScopeInvalidation:
    """Apply a scope delta without discarding unrelated evidence or layers."""

    retained = tuple(ref for ref in state.evidence_refs if ref not in invalidated_refs)
    invalidated = tuple(ref for ref in state.evidence_refs if ref in invalidated_refs)
    state.evidence_refs = list(retained)
    for collection_name in ("feature_refs", "layer_refs", "renderable_refs"):
        collection = getattr(state.geospatial_state, collection_name)
        setattr(
            state.geospatial_state,
            collection_name,
            [ref for ref in collection if ref not in invalidated_refs],
        )
    if new_scope is not None:
        state.geospatial_state.geographic_scope = new_scope
    state.revision += 1
    return ScopeInvalidation(invalidated, retained)

###############################################################################
def apply_steering_delta(state: AgentThreadState, delta: Any) -> AgentThreadState:
    """Apply a classified follow-up without rebuilding unrelated evidence."""

    kind = str(getattr(delta, "kind", "instruction"))
    text = str(getattr(delta, "text", "")).strip()
    parameters = cast(dict[str, Any], getattr(delta, "parameters", {}))
    state.revision += 1
    if kind in {"scope_change", "exclusion"}:
        invalidated_refs: set[str] = set()
        for task in state.tasks:
            if task.status == "completed" and task.kind not in {"location_resolution", "comparison"}:
                task.scope_revision = state.revision
                task.status = "superseded"
                invalidated_refs.update(task.output_refs)
        if invalidated_refs:
            invalidate_scope_evidence(state, invalidated_refs=invalidated_refs)
        radius_text: Any = parameters.get("radius_text")
        if isinstance(radius_text, str):
            match = re.search(r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>km|mi|miles?)", radius_text.lower())
            if match is not None:
                value = float(match.group("value"))
                multiplier = 1_609.344 if match.group("unit").startswith("mi") else 1_000.0
                state.geospatial_state.geographic_scope.radius_m = value * multiplier
        state.geospatial_state.geographic_scope.exclusions.extend(
            [{"text": text}] if kind == "exclusion" else []
        )
    elif kind == "add_dataset":
        state.tasks.append(
            AgentTask(
                id=f"steering-{state.revision}",
                description=text or "Retrieve the requested additional dataset.",
                kind="dataset_enrichment",
                depends_on=[state.active_task_id] if state.active_task_id else [],
                scope_revision=state.revision,
            )
        )
    elif kind == "comparison":
        if not any(task.kind == "comparison" and task.status == "pending" for task in state.tasks):
            state.tasks.append(
                AgentTask(
                    id=f"comparison-{state.revision}",
                    description=text or "Compare retained candidate evidence.",
                    kind="comparison",
                    depends_on=[task.id for task in state.tasks if task.required and task.status == "completed"],
                    scope_revision=state.revision,
                )
            )
    elif kind == "clarification":
        state.unresolved_questions.append(text)
    validate_task_graph(state.tasks)
    return state
