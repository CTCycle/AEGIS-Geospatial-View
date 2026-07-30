from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from server.domain.agent.actions import AgentAction

###############################################################################
class LLMTemporalSignal(BaseModel):
    model_config = ConfigDict(extra="ignore")

    mode: Literal["current", "historical", "forecast", "none"] = "none"
    raw_text: str | None = None
    reference_time_iso: str | None = None

###############################################################################
class LLMLocationSignal(BaseModel):
    model_config = ConfigDict(extra="ignore")

    signal_type: Literal[
        "address",
        "city",
        "country",
        "coordinates",
        "deictic",
        "poi",
        "region",
        "street",
    ] = "address"
    raw_value: str = ""
    normalized_value: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

###############################################################################
class LLMDisallowedPattern(BaseModel):
    model_config = ConfigDict(extra="ignore")

    pattern_id: str
    reason: str
    matched_text: str

###############################################################################
class LLMAtomicTask(BaseModel):
    model_config = ConfigDict(extra="ignore")

    summary: str
    task_type: str = "unknown"
    intent: str = "unknown"
    required_entities: list[str] = Field(default_factory=list)
    required_layers: list[str] = Field(default_factory=list)
    visualization_changes: dict[str, Any] = Field(default_factory=dict)

###############################################################################
class LLMClarificationOption(BaseModel):
    model_config = ConfigDict(extra="ignore")

    option_id: str
    label: str
    description: str | None = None

###############################################################################
class LLMClarificationPlan(BaseModel):
    model_config = ConfigDict(extra="ignore")

    question: str
    reason: str
    blocking_fields: list[str] = Field(default_factory=list)
    options: list[LLMClarificationOption] = Field(default_factory=list)
    preserve_valid_results: bool = True
    apply_visualization_changes: bool = False

###############################################################################
class LLMViewportIntent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    scope: Literal[
        "preserve_current",
        "building",
        "street",
        "neighborhood",
        "district",
        "city",
        "region",
        "country",
        "auto",
    ] = "auto"
    tighten_relative_to_active: bool = False
    radius_hint_m: float | None = Field(default=None, gt=0.0)
    reason: str | None = None

###############################################################################
class LLMParserExtraction(BaseModel):
    model_config = ConfigDict(extra="ignore")

    task_class: Literal["map_search", "direct_query", "general_question", "unclear"] = "unclear"
    action_id: str = AgentAction.UNKNOWN.value
    action_label: str = "General map request"
    task_tags: list[str] = Field(default_factory=list)
    action_tags: list[str] = Field(default_factory=list)
    requested_visualizations: list[str] = Field(default_factory=list)
    requires_location: bool = True
    location_signals: list[LLMLocationSignal] = Field(default_factory=list)
    temporal_signal: LLMTemporalSignal = Field(default_factory=LLMTemporalSignal)
    ambiguities: list[str] = Field(default_factory=list)
    disallowed_patterns: list[LLMDisallowedPattern] = Field(default_factory=list)
    parser_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    relationship: Literal[
        "new_task",
        "follow_up",
        "correction",
        "clarification",
        "qa",
        "simple_chat",
        "failure_inquiry",
    ] = "new_task"
    map_target: str | None = None
    entity_target: str | None = None
    requested_layers: list[str] = Field(default_factory=list)
    poi_categories: list[Literal["bicycle_parking", "transit_stops", "rail_stations"]] = Field(default_factory=list)
    requested_basemap: str | None = None
    requested_attributes: list[str] = Field(default_factory=list)
    required_data_sources: list[str] = Field(default_factory=list)
    required_tool_category: str | None = None
    tools_needed: bool = False
    direct_response_sufficient: bool = False
    requires_reparse: bool = False
    capability_limitations: list[str] = Field(default_factory=list)
    expected_frontend_update: str = "assistant_message"
    atomic_tasks: list[LLMAtomicTask] = Field(default_factory=list)
    clarification_plan: LLMClarificationPlan | None = None
    viewport_intent: LLMViewportIntent | None = None
