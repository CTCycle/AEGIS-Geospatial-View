from __future__ import annotations

from typing import Literal

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

    signal_type: Literal["address", "city", "country", "coordinates", "deictic"] = "address"
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
