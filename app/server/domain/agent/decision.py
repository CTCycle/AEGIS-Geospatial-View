from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from server.domain.agent.actions import AgentAction

PlanState = Literal["clarify", "direct_response", "direct_tool", "map_search", "reject"]
ExecutionMode = Literal["direct_text", "map"]

###############################################################################
class ClarificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str
    reason: str
    missing_fields: list[str] = Field(default_factory=list)

###############################################################################
class CapabilityCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capability_id: str
    kind: Literal["basemap", "overlay", "tool"]
    provider: str
    score: float = 0.0
    supports_map: bool = True
    supports_direct_text: bool = False

###############################################################################
class ResolvedLocation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    country: str | None = None
    city: str | None = None
    address: str | None = None
    source: str = "resolver"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

###############################################################################
class ExecutionPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: PlanState
    mode: ExecutionMode | None = None
    action_id: str
    temporal_mode: str | None = None
    temporal_text: str | None = None
    basemap_id: str | None = None
    overlay_ids: list[str] = Field(default_factory=list)
    tool_id: str | None = None

###############################################################################
class AgentToolCallPlanItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str
    reason: str
    required: bool = True

###############################################################################
class AgentDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: AgentAction
    action_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    tool_names: list[str] = Field(default_factory=list)
    tool_call_plan: list[AgentToolCallPlanItem] = Field(default_factory=list)
    requires_clarification: bool = False
    clarification_question: str | None = None

###############################################################################
class DecisionTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    steps: list[str] = Field(default_factory=list)

###############################################################################
class PolicyDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan: ExecutionPlan
    clarification: ClarificationRequest | None = None
    resolved_location: ResolvedLocation | None = None
    candidates: list[CapabilityCandidate] = Field(default_factory=list)
    trace: DecisionTrace = Field(default_factory=DecisionTrace)

    @property
    def selected_action(self) -> str:
        return self.plan.action_id

    @property
    def action_confidence(self) -> float:
        return 1.0

    @property
    def selected_tool_names(self) -> list[str]:
        return [self.plan.tool_id] if self.plan.tool_id else []

    @property
    def requires_location_resolution(self) -> bool:
        return self.resolved_location is None and self.plan.state in {"clarify", "map_search"}

    @property
    def requires_overlay_resolution(self) -> bool:
        return bool(self.plan.overlay_ids)

    @property
    def requires_external_source_query(self) -> bool:
        return self.plan.action_id == AgentAction.MAP_EXTERNAL_SOURCE_COMBINATION.value

    @property
    def requires_user_clarification(self) -> bool:
        return self.clarification is not None
