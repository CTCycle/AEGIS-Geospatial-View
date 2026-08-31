from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from server.common.time import utc_now
from server.domain.agent.runtime import (
    AgentGoal,
    AgentTask,
    GeospatialWorkingState,
)

TaskRelationship = Literal[
    "new_task",
    "follow_up",
    "correction",
    "clarification",
    "qa",
    "simple_chat",
    "failure_inquiry",
]
TaskStatus = Literal[
    "pending",
    "needs_clarification",
    "routed",
    "in_progress",
    "completed",
    "failed",
    "skipped",
]
SpecialistGroup = Literal[
    "direct_chat",
    "failure_diagnostics",
    "place_resolution",
    "geospatial_features",
    "map_layers",
    "environmental_data",
    "visualization_update",
]


###############################################################################
class TaskFailureDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: str
    component: str | None = None
    tool_name: str | None = None
    sanitized_error: str
    missing_input: list[str] = Field(default_factory=lambda: list[str]())
    unsupported_capability: str | None = None
    partial_results_available: bool = False
    recovery_suggestion: str | None = None
    user_explanation: str
    provider_error: dict[str, object] | None = None
    failure_category: (
        Literal[
            "model_capability",
            "provider_api",
            "schema_definition",
            "response_parsing",
            "context_limit",
        ]
        | None
    ) = None


###############################################################################
class ToolRetryPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_attempts: int = Field(default=2, ge=1, le=3)
    retryable_error_codes: list[str] = Field(
        default_factory=lambda: [
            "tool_timeout",
            "provider_timeout",
            "rate_limited",
            "provider_unavailable",
        ]
    )


###############################################################################
class ToolInputBinding(BaseModel):
    """Bind a value produced by a predecessor into a later tool call."""

    model_config = ConfigDict(extra="forbid")

    target: str = Field(min_length=1)
    source_step_id: str = Field(min_length=1)
    source_path: str = "data"
    required: bool = True


###############################################################################
class ToolPlanStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: str
    tool_name: str
    capability_id: str | None = None
    reason: str
    arguments: dict[str, Any] = Field(default_factory=lambda: dict[str, Any]())
    depends_on: list[str] = Field(default_factory=lambda: list[str]())
    input_bindings: list[ToolInputBinding] = Field(
        default_factory=lambda: list[ToolInputBinding]()
    )
    output_refs: list[str] = Field(default_factory=lambda: list[str]())
    parallel_group: str | None = None
    timeout_seconds: int = Field(default=30, ge=1, le=120)
    retry_policy: ToolRetryPolicy = Field(default_factory=ToolRetryPolicy)
    validation_policy: str = "validate_tool_envelope_and_declared_output"
    fallback_behavior: str = "fail_required_step"
    expected_output_schema: str = "tool_execution_envelope"
    merge_policy: str = "merge_verified_map_or_direct_result"
    required: bool = True


###############################################################################
class ToolPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_group: SpecialistGroup
    candidate_tools: list[str] = Field(default_factory=lambda: list[str]())
    selected_tools: list[str] = Field(default_factory=lambda: list[str]())
    steps: list[ToolPlanStep] = Field(default_factory=lambda: list[ToolPlanStep]())
    visualization_update: dict[str, Any] = Field(
        default_factory=lambda: dict[str, Any]()
    )
    frontend_derivation: str = "derive_from_validated_results"
    partial_failure_policy: str = "retain_successful_required_results"


###############################################################################
class ConversationTaskRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str
    raw_user_text: str
    prompt_summary: str
    normalized_description: str
    task_type: str
    intent: str
    relationship: TaskRelationship
    required_entities: list[str] = Field(default_factory=lambda: list[str]())
    geographic_scope: dict[str, Any] | None = None
    required_data_layers: list[str] = Field(default_factory=lambda: list[str]())
    visualization_changes: dict[str, Any] = Field(
        default_factory=lambda: dict[str, Any]()
    )
    specialist: SpecialistGroup
    tool_plan: ToolPlan | None = None
    tool_result_refs: list[str] = Field(default_factory=lambda: list[str]())
    status: TaskStatus = "pending"
    is_current: bool = True
    parent_task_id: str | None = None
    blocking_ambiguity: str | None = None
    failure: TaskFailureDetail | None = None
    progress_summary: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


###############################################################################
class ToolResultProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str
    capability_id: str | None = None
    provider: str | None = None
    attempt: int = 1
    elapsed_ms: int = 0
    call_fingerprint: str | None = None
    fetched_at: datetime = Field(default_factory=utc_now)
    observation_time: str | None = None
    coverage: dict[str, Any] | None = None
    spatial_resolution: str | None = None
    units: dict[str, str] = Field(default_factory=lambda: dict[str, str]())
    source_url: str | None = None
    result_status: str = "unknown"
    result_type: str = "unknown"
    partial: bool = False
    warnings: list[str] = Field(default_factory=lambda: list[str]())


###############################################################################
class PlannedToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: str
    ok: bool
    data: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None
    validation_error: str | None = None
    provenance: ToolResultProvenance


###############################################################################
class VisualizationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    basemap_replacement: str | None = None
    add_layer_ids: list[str] = Field(default_factory=lambda: list[str]())
    remove_layer_ids: list[str] = Field(default_factory=lambda: list[str]())
    replace_layer_ids: dict[str, str] = Field(default_factory=lambda: dict[str, str]())
    collection_id: str = "active-map"
    collection_revision: int | None = None
    added_instance_ids: list[str] = Field(default_factory=lambda: list[str]())
    removed_instance_ids: list[str] = Field(default_factory=lambda: list[str]())
    updated_instance_ids: list[str] = Field(default_factory=lambda: list[str]())
    unmatched_selectors: list[str] = Field(default_factory=lambda: list[str]())
    ambiguous_selectors: list[str] = Field(default_factory=lambda: list[str]())
    clarification: str | None = None


###############################################################################
class ConversationTaskSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[3] = 3
    conversation_key: str
    current_task_id: str | None = None
    goal: AgentGoal | None = None
    tasks: list[AgentTask] = Field(default_factory=lambda: list[AgentTask]())
    geospatial_state: GeospatialWorkingState = Field(
        default_factory=GeospatialWorkingState
    )
    evidence_refs: list[str] = Field(default_factory=list)
    active_map_session: dict[str, Any] | None = None
    assumptions: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    conversation_summary: dict[str, Any] | None = None
