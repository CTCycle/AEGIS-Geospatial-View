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
class NormalizedAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_id: str
    action_label: str
    task_tags: list[str] = Field(default_factory=list)
    action_tags: list[str] = Field(default_factory=list)
    requested_visualizations: list[str] = Field(default_factory=list)
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
    normalized_action: NormalizedAction
    temporal_signal: TemporalSignal = Field(default_factory=TemporalSignal)
    ambiguities: list[str] = Field(default_factory=list)
    disallowed_patterns: list[DisallowedPattern] = Field(default_factory=list)
    parser_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    
