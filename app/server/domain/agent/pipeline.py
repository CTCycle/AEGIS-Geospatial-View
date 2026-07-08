from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from server.common.time import utc_now

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
    missing_input: list[str] = Field(default_factory=list)
    unsupported_capability: str | None = None
    partial_results_available: bool = False
    recovery_suggestion: str | None = None
    user_explanation: str

###############################################################################
class ToolRetryPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_attempts: int = Field(default=2, ge=1, le=3)
    retryable_error_codes: list[str] = Field(
        default_factory=lambda: [
            "tool_timeout",
            "provider_timeout",
            "provider_rate_limited",
            "provider_unavailable",
        ]
    )

###############################################################################
class ToolPlanStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: str
    tool_name: str
    capability_id: str | None = None
    reason: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)
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
    candidate_tools: list[str] = Field(default_factory=list)
    selected_tools: list[str] = Field(default_factory=list)
    steps: list[ToolPlanStep] = Field(default_factory=list)
    visualization_update: dict[str, Any] = Field(default_factory=dict)
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
    required_entities: list[str] = Field(default_factory=list)
    geographic_scope: dict[str, Any] | None = None
    required_data_layers: list[str] = Field(default_factory=list)
    visualization_changes: dict[str, Any] = Field(default_factory=dict)
    specialist: SpecialistGroup
    tool_plan: ToolPlan | None = None
    tool_result_refs: list[str] = Field(default_factory=list)
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
    add_layer_ids: list[str] = Field(default_factory=list)
    remove_layer_ids: list[str] = Field(default_factory=list)
    replace_layer_ids: dict[str, str] = Field(default_factory=dict)

###############################################################################
class ConversationTaskSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation_key: str
    current_task_id: str | None = None
    tasks: list[ConversationTaskRecord] = Field(default_factory=list)
    active_visualization: dict[str, Any] | None = None
