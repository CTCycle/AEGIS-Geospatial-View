from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

TaskClass = Literal["map_search", "direct_query", "general_question", "unclear"]
PoiCategory = Literal["bicycle_parking", "transit_stops", "rail_stations"]
LocationSignalType = Literal[
    "address",
    "city",
    "country",
    "coordinates",
    "deictic",
    "poi",
    "region",
    "street",
]
TemporalMode = Literal["current", "historical", "forecast", "none"]
OverlayAction = Literal["add", "remove", "keep_only", "show", "hide", "update"]
OverlayScopeKind = Literal["global", "current_view", "location"]
OverlayVisibility = Literal["any", "visible", "hidden"]

###############################################################################
class ConversationContextSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recent_messages: list[dict[str, str]] = Field(default_factory=lambda: list[dict[str, str]]())
    memory_snapshot: dict[str, object] = Field(default_factory=lambda: dict[str, object]())

###############################################################################
class LocationSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signal_type: LocationSignalType
    raw_value: str
    normalized_value: str | None = None
    latitude: float | None = Field(default=None, ge=-90.0, le=90.0)
    longitude: float | None = Field(default=None, ge=-180.0, le=180.0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source: Literal["text", "memory", "model"] = "text"

###############################################################################
class TemporalSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: TemporalMode = "none"
    raw_text: str | None = None
    reference_time_iso: str | None = None

###############################################################################
class NormalizedAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_id: str
    action_label: str
    task_tags: list[str] = Field(default_factory=lambda: list[str]())
    action_tags: list[str] = Field(default_factory=lambda: list[str]())
    requested_visualizations: list[str] = Field(default_factory=lambda: list[str]())
    requires_location: bool = True

###############################################################################
class DisallowedPattern(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pattern_id: str
    reason: str
    matched_text: str

###############################################################################
class ViewportIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

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
class OverlaySelector(BaseModel):
    """Typed selector for overlay instances and catalog capabilities.

    Selectors deliberately keep the matching dimensions independent.  The
    resolver can therefore report an unmatched or ambiguous dimension without
    falling back to scanning the user's prose for layer names.
    """

    model_config = ConfigDict(extra="forbid")

    instance_ids: list[str] = Field(default_factory=lambda: list[str]())
    capability_ids: list[str] = Field(default_factory=lambda: list[str]())
    concepts: list[str] = Field(default_factory=lambda: list[str]())
    labels: list[str] = Field(default_factory=lambda: list[str]())
    providers: list[str] = Field(default_factory=lambda: list[str]())
    overlay_types: list[str] = Field(default_factory=lambda: list[str]())
    rendering_modes: list[str] = Field(default_factory=lambda: list[str]())
    tags: list[str] = Field(default_factory=lambda: list[str]())
    visibility: OverlayVisibility = "any"

###############################################################################
class OverlayScope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: OverlayScopeKind = "global"
    # A resolved location is represented as a bounded JSON object here so the
    # extraction contract does not depend on the geospatial domain module.
    location: dict[str, Any] | None = None
    label: str | None = None

###############################################################################
class OverlayPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    opacity: float | None = Field(default=None, ge=0.0, le=1.0)
    time: str | None = None
    style: str | None = None
    format: str | None = None

###############################################################################
class OverlayStateReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    collection_id: str = "active-map"
    revision: int = Field(default=0, ge=0)

###############################################################################
class OverlayCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: OverlayAction
    selector: OverlaySelector = Field(default_factory=OverlaySelector)
    scope: OverlayScope = Field(default_factory=OverlayScope)
    patch: OverlayPatch = Field(default_factory=OverlayPatch)
    state_reference: OverlayStateReference = Field(default_factory=OverlayStateReference)

###############################################################################
class TurnParseResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_text: str
    conversation_context: ConversationContextSnapshot
    task_class: TaskClass
    location_signals: list[LocationSignal] = Field(default_factory=lambda: list[LocationSignal]())
    normalized_action: NormalizedAction
    temporal_signal: TemporalSignal = Field(default_factory=TemporalSignal)
    ambiguities: list[str] = Field(default_factory=lambda: list[str]())
    disallowed_patterns: list[DisallowedPattern] = Field(default_factory=lambda: list[DisallowedPattern]())
    parser_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
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
    requested_layers: list[str] = Field(default_factory=lambda: list[str]())
    overlay_commands: list[OverlayCommand] = Field(default_factory=lambda: list[OverlayCommand]())
    poi_categories: list[PoiCategory] = Field(default_factory=lambda: list[PoiCategory]())
    requested_basemap: str | None = None
    requested_attributes: list[str] = Field(default_factory=lambda: list[str]())
    required_data_sources: list[str] = Field(default_factory=lambda: list[str]())
    required_tool_category: str | None = None
    tools_needed: bool = False
    direct_response_sufficient: bool = False
    requires_reparse: bool = False
    capability_limitations: list[str] = Field(default_factory=lambda: list[str]())
    expected_frontend_update: str = "assistant_message"
    atomic_tasks: list[dict[str, Any]] = Field(default_factory=lambda: list[dict[str, Any]]())
    clarification_plan: dict[str, Any] | None = None
    viewport_intent: ViewportIntent | None = None
    provider_error: dict[str, Any] | None = None
    failure_category: Literal[
        "model_capability",
        "provider_api",
        "schema_definition",
        "response_parsing",
        "context_limit",
    ] | None = None
