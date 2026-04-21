from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

TaskClass = Literal["map_search", "direct_query", "general_question", "unclear"]
LocationSignalType = Literal["address", "city", "country", "coordinates", "deictic"]
TemporalMode = Literal["current", "historical", "forecast", "none"]

###############################################################################
class ConversationContextSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: int | None = None
    recent_messages: list[dict[str, str]] = Field(default_factory=list)
    memory_snapshot: dict[str, object] = Field(default_factory=dict)


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
class NormalizedIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent_id: str
    intent_label: str
    task_tags: list[str] = Field(default_factory=list)
    intent_tags: list[str] = Field(default_factory=list)
    requires_location: bool = True

###############################################################################
class DisallowedPattern(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pattern_id: str
    reason: str
    matched_text: str

###############################################################################
class TurnParseResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_text: str
    conversation_context: ConversationContextSnapshot
    task_class: TaskClass
    location_signals: list[LocationSignal] = Field(default_factory=list)
    normalized_intent: NormalizedIntent
    temporal_signal: TemporalSignal = Field(default_factory=TemporalSignal)
    ambiguities: list[str] = Field(default_factory=list)
    disallowed_patterns: list[DisallowedPattern] = Field(default_factory=list)
    parser_confidence: float = Field(default=0.0, ge=0.0, le=1.0)


# -----------------------------------------------------------------------------
# Legacy compatibility models retained only for internal transitional imports.
class ExtractedLocation(BaseModel):
    address: str | None = None
    city: str | None = None
    country: str | None = None


class ExtractedCoordinates(BaseModel):
    longitude: float | None = None
    latitude: float | None = None


class ExtractedTimeReferences(BaseModel):
    year: int | None = None
    month: int | None = None
    day: int | None = None
    time_range: bool = False
    start_time: list[str] = Field(default_factory=list)
    end_time: list[str] = Field(default_factory=list)


class ExtractedIntent(BaseModel):
    location: ExtractedLocation = Field(default_factory=ExtractedLocation)
    coordinates: ExtractedCoordinates = Field(default_factory=ExtractedCoordinates)
    location_type: str | None = None
    base_map_type: str | None = None
    time_references: ExtractedTimeReferences = Field(default_factory=ExtractedTimeReferences)
    user_goal: str = Field(default="", max_length=1000)
    filters: list[str] = Field(default_factory=list)
    area_of_interest: str | None = None
    certainty: float = Field(default=0.0, ge=0.0, le=1.0)


class ExtractedIntentPatch(BaseModel):
    location: ExtractedLocation | None = None
    coordinates: ExtractedCoordinates | None = None
    location_type: str | None = None
    base_map_type: str | None = None
    time_references: ExtractedTimeReferences | None = None
    user_goal: str | None = Field(default=None, max_length=1000)
    filters: list[str] | None = None
    area_of_interest: str | None = None
    certainty: float | None = Field(default=None, ge=0.0, le=1.0)


class StageAParserIntent(BaseModel):
    has_location: bool = False
    location_type: str | None = None
    has_time_reference: bool = False
    requires_search: bool = False
    requires_data: bool = False
    required_tools: list[str] = Field(default_factory=list)
    certainty: float = Field(default=0.0, ge=0.0, le=1.0)


class StageBLocation(BaseModel):
    address: str | None = None
    city: str | None = None
    country: str | None = None
    location_type: str | None = None


class StageBCoordinates(BaseModel):
    latitude: float | None = None
    longitude: float | None = None


class StageBSearchExtraction(BaseModel):
    location: StageBLocation = Field(default_factory=StageBLocation)
    coordinates: StageBCoordinates = Field(default_factory=StageBCoordinates)
    time_reference: str | None = None
    base_map: str | None = None
    required_overlays: list[str] = Field(default_factory=list)
