from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

AgentDecisionType = Literal["clarify", "search_with_follow_up", "search_and_complete"]
ExecutionMode = Literal["clarify", "geocode", "search"]
LocationStatus = Literal["missing", "partial", "valid"]

###############################################################################
class ChatInstructionPayload(BaseModel):
    tone: str = "clear_and_direct"
    must_explain_limitations: bool = True
    must_offer_refinements: bool = True
    must_confirm_search_start: bool = False

###############################################################################
class Feasibility(BaseModel):
    is_supported: bool = True
    blocking_reason: str | None = None

###############################################################################
class AgentDecision(BaseModel):
    decision: AgentDecisionType
    execution_mode: ExecutionMode = "clarify"
    tool_target: str | None = None
    should_trigger_search: bool
    location_status: LocationStatus
    requires_geocoding: bool
    selected_basemap_id: str | None = None
    selected_overlay_ids: list[str] = Field(default_factory=list)
    clarification_question: str | None = None
    chat_instructions: ChatInstructionPayload = Field(default_factory=ChatInstructionPayload)
    reasoning_summary: str = ""
    feasibility: Feasibility = Field(default_factory=Feasibility)
