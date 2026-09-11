from __future__ import annotations

from typing import Any, Literal, cast, get_args

from pydantic import BaseModel, ConfigDict, Field, model_validator

from server.domain.agent.actions import AgentAction

###############################################################################
_NULL_SENTINELS = frozenset({"null", "none", "nil"})


###############################################################################
class _ExtractionModel(BaseModel):
    """Shared provider-boundary normalization for typed parser payloads.

    Some OpenAI-compatible providers serialize a JSON null for an optional
    field as a textual sentinel.  Normalize that representation only when the
    destination field explicitly permits ``None``; required text fields and
    enum values therefore remain strict.
    """

    # -------------------------------------------------------------------------
    @model_validator(mode="before")
    @classmethod
    def _normalize_nullable_sentinels(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        normalized: dict[str, Any] = dict(cast(Any, value))
        for name, field in cls.model_fields.items():
            raw: Any = normalized.get(name)
            if (
                isinstance(raw, str)
                and raw.strip().casefold() in _NULL_SENTINELS
                and type(None) in get_args(field.annotation)
            ):
                normalized[name] = None
        return normalized


###############################################################################
class LLMTemporalSignal(_ExtractionModel):
    model_config = ConfigDict(extra="ignore")

    mode: Literal["current", "historical", "forecast", "none"] = "none"
    raw_text: str | None = None
    reference_time_iso: str | None = None
    start_time_iso: str | None = None
    end_time_iso: str | None = None
    granularity: Literal[
        "instant", "hour", "day", "month", "year", "custom", "none"
    ] = "none"
    aggregation: Literal["none", "instant", "sum", "mean", "min", "max", "count"] = (
        "none"
    )

###############################################################################
class LLMGeographicRelationship(_ExtractionModel):
    model_config = ConfigDict(extra="ignore")

    relationship: str = "in"
    target: str = ""
    reference: str | None = None
    analysis_scope: str = "bbox"
    distance_m: float | None = Field(default=None, gt=0.0)

###############################################################################
class LLMContextQuery(_ExtractionModel):
    model_config = ConfigDict(extra="ignore")

    kind: Literal[
        "none",
        "active_location",
        "active_overlays",
        "active_map_summary",
        "previous_user_request",
        "capabilities",
        "failure",
    ] = "none"

###############################################################################
class LLMLocationSignal(_ExtractionModel):
    model_config = ConfigDict(extra="ignore")

    signal_type: Literal[
        "address",
        "airport",
        "city",
        "country",
        "coordinates",
        "deictic",
        "poi",
        "feature",
        "landmark",
        "region",
        "river",
        "road",
        "street",
        "station",
        "neighborhood",
        "district",
        "municipality",
        "county",
        "province",
        "state",
    ] = "address"
    raw_value: str = ""
    normalized_value: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

###############################################################################
class LLMDisallowedPattern(_ExtractionModel):
    model_config = ConfigDict(extra="ignore")

    pattern_id: str
    reason: str
    matched_text: str

###############################################################################
class LLMAtomicTask(_ExtractionModel):
    model_config = ConfigDict(extra="ignore")

    summary: str
    id: str | None = None
    task_type: str = "unknown"
    intent: str = "unknown"
    kind: str = "research"
    depends_on: list[str] = Field(default_factory=lambda: list[str]())
    required: bool = True
    input_refs: list[str] = Field(default_factory=lambda: list[str]())
    output_refs: list[str] = Field(default_factory=lambda: list[str]())
    required_entities: list[str] = Field(default_factory=lambda: list[str]())
    required_layers: list[str] = Field(default_factory=lambda: list[str]())
    visualization_changes: dict[str, Any] = Field(
        default_factory=lambda: dict[str, Any]()
    )

###############################################################################
class LLMClarificationOption(_ExtractionModel):
    model_config = ConfigDict(extra="ignore")

    option_id: str
    label: str
    description: str | None = None

###############################################################################
class LLMClarificationPlan(_ExtractionModel):
    model_config = ConfigDict(extra="ignore")

    question: str
    reason: str
    blocking_fields: list[str] = Field(default_factory=lambda: list[str]())
    options: list[LLMClarificationOption] = Field(
        default_factory=lambda: list[LLMClarificationOption]()
    )
    preserve_valid_results: bool = True
    apply_visualization_changes: bool = False

###############################################################################
class LLMViewportIntent(_ExtractionModel):
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
class LLMOverlaySelector(_ExtractionModel):
    model_config = ConfigDict(extra="ignore")

    instance_ids: list[str] = Field(default_factory=lambda: list[str]())
    capability_ids: list[str] = Field(default_factory=lambda: list[str]())
    concepts: list[str] = Field(default_factory=lambda: list[str]())
    labels: list[str] = Field(default_factory=lambda: list[str]())
    providers: list[str] = Field(default_factory=lambda: list[str]())
    overlay_types: list[str] = Field(default_factory=lambda: list[str]())
    rendering_modes: list[str] = Field(default_factory=lambda: list[str]())
    tags: list[str] = Field(default_factory=lambda: list[str]())
    visibility: Literal["any", "visible", "hidden"] = "any"

###############################################################################
class LLMOverlayScope(_ExtractionModel):
    model_config = ConfigDict(extra="ignore")

    kind: Literal["global", "current_view", "location"] = "global"
    location: dict[str, Any] | None = None
    label: str | None = None

###############################################################################
class LLMOverlayPatch(_ExtractionModel):
    model_config = ConfigDict(extra="ignore")

    opacity: float | None = Field(default=None, ge=0.0, le=1.0)
    time: str | None = None
    style: str | None = None
    format: str | None = None

###############################################################################
class LLMOverlayStateReference(_ExtractionModel):
    model_config = ConfigDict(extra="ignore")

    collection_id: str = "active-map"
    revision: int = Field(default=0, ge=0)

###############################################################################
class LLMOverlayCommand(_ExtractionModel):
    model_config = ConfigDict(extra="ignore")

    action: Literal["add", "remove", "keep_only", "show", "hide", "update"]
    selector: LLMOverlaySelector = Field(default_factory=LLMOverlaySelector)
    scope: LLMOverlayScope = Field(default_factory=LLMOverlayScope)
    # Providers may emit an explicit null for commands without a patch. The
    # parser boundary normalizes that representation to an empty patch.
    patch: LLMOverlayPatch | None = None
    state_reference: LLMOverlayStateReference = Field(
        default_factory=LLMOverlayStateReference
    )

###############################################################################
class LLMParserExtraction(_ExtractionModel):
    model_config = ConfigDict(extra="ignore")

    task_class: Literal["map_search", "direct_query", "general_question", "unclear"] = (
        "unclear"
    )
    action_id: str = AgentAction.UNKNOWN.value
    action_label: str = "General map request"
    task_tags: list[str] = Field(default_factory=lambda: list[str]())
    action_tags: list[str] = Field(default_factory=lambda: list[str]())
    requested_visualizations: list[str] = Field(default_factory=lambda: list[str]())
    requires_location: bool = True
    location_signals: list[LLMLocationSignal] = Field(
        default_factory=lambda: list[LLMLocationSignal]()
    )
    temporal_signal: LLMTemporalSignal = Field(default_factory=LLMTemporalSignal)
    geographic_relationships: list[LLMGeographicRelationship] = Field(
        default_factory=lambda: list[LLMGeographicRelationship]()
    )
    operations: list[str] = Field(default_factory=lambda: list[str]())
    filters: dict[str, Any] = Field(default_factory=lambda: dict[str, Any]())
    presentation_requirements: dict[str, Any] = Field(
        default_factory=lambda: dict[str, Any]()
    )
    context_query: LLMContextQuery = Field(default_factory=LLMContextQuery)
    ambiguities: list[str] = Field(default_factory=lambda: list[str]())
    disallowed_patterns: list[LLMDisallowedPattern] = Field(
        default_factory=lambda: list[LLMDisallowedPattern]()
    )
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
    requested_concepts: list[str] = Field(default_factory=lambda: list[str]())
    requested_layers: list[str] = Field(default_factory=lambda: list[str]())
    overlay_commands: list[LLMOverlayCommand] = Field(
        default_factory=lambda: list[LLMOverlayCommand](),
        description=(
            "One typed command for every independent map mutation in the current "
            "request, including mutations that can be applied while another data "
            "request is unsupported."
        ),
    )
    poi_categories: list[str] = Field(default_factory=lambda: list[str]())
    radius_m: float | None = Field(default=None, gt=0.0)
    result_limit: int | None = Field(default=None, ge=1, le=500)
    presentation_mode: Literal["text", "map", "both"] = "map"
    requested_basemap: str | None = None
    requested_attributes: list[str] = Field(default_factory=lambda: list[str]())
    required_data_sources: list[str] = Field(default_factory=lambda: list[str]())
    required_tool_category: str | None = None
    tools_needed: bool = False
    direct_response_sufficient: bool = False
    requires_reparse: bool = False
    capability_limitations: list[str] = Field(default_factory=lambda: list[str]())
    expected_frontend_update: str = "assistant_message"
    atomic_tasks: list[LLMAtomicTask] = Field(
        default_factory=lambda: list[LLMAtomicTask]()
    )
    clarification_plan: LLMClarificationPlan | None = None
    viewport_intent: LLMViewportIntent | None = None

###############################################################################
class LLMParserExtractionProviderContract(LLMParserExtraction):
    """Provider-facing contract with a required semantic envelope.

    The normalized extraction model keeps defaults for deterministic internal
    fixtures. Provider responses must explicitly provide these fields so a
    sparse JSON object cannot be accepted as a usable interpretation.
    """

    task_class: Literal["map_search", "direct_query", "general_question", "unclear"] = Field(...)  # pyright: ignore[reportGeneralTypeIssues]
    action_id: str = Field(...)  # pyright: ignore[reportGeneralTypeIssues]
    requires_location: bool = Field(...)  # pyright: ignore[reportGeneralTypeIssues]
    parser_confidence: float = Field(..., ge=0.0, le=1.0)  # pyright: ignore[reportGeneralTypeIssues]
    relationship: Literal[  # pyright: ignore[reportGeneralTypeIssues]
        "new_task",
        "follow_up",
        "correction",
        "clarification",
        "qa",
        "simple_chat",
        "failure_inquiry",
    ] = Field(...)  # pyright: ignore[reportGeneralTypeIssues]
    presentation_mode: Literal["text", "map", "both"] = Field(...)  # pyright: ignore[reportGeneralTypeIssues]
