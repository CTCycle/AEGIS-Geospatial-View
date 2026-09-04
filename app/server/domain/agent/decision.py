from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from server.common.time import utc_now
from server.domain.agent.actions import AgentAction

PlanState = Literal["clarify", "direct_response", "direct_tool", "map_search", "reject"]
ExecutionMode = Literal["direct_text", "map"]


###############################################################################
class ClarificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str
    reason: str
    missing_fields: list[str] = Field(default_factory=lambda: list[str]())


###############################################################################
class LocationResolutionProvenance(BaseModel):
    """Provider evidence for a location resolved outside the tool registry."""

    model_config = ConfigDict(extra="forbid")

    provider: str
    source_url: str | None = None
    fetched_at: datetime = Field(default_factory=utc_now)
    result_status: str = "ok"
    result_type: str = "location"


###############################################################################
class LocationHierarchyEntry(BaseModel):
    """One user/entity signal retained in the resolved location hierarchy."""

    model_config = ConfigDict(extra="forbid")

    signal_type: str
    raw_value: str
    normalized_value: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source: str = "text"
    canonical_label: str | None = None


###############################################################################
class LocationHierarchy(BaseModel):
    """The single target and its geographic parent context."""

    model_config = ConfigDict(extra="forbid")

    target: LocationHierarchyEntry
    parents: list[LocationHierarchyEntry] = Field(
        default_factory=list[LocationHierarchyEntry]
    )


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
    location_type: str | None = None
    location_class: str | None = None
    bbox: list[float] | None = None
    bbox_source: str | None = None
    provenance: LocationResolutionProvenance | None = None
    hierarchy: LocationHierarchy | None = None


###############################################################################
class ExecutionPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: PlanState
    mode: ExecutionMode | None = None
    action_id: str
    temporal_mode: str | None = None
    temporal_text: str | None = None
    temporal_reference_time_iso: str | None = None
    tool_arguments: dict[str, object] = Field(
        default_factory=lambda: dict[str, object]()
    )
    basemap_id: str | None = None
    overlay_ids: list[str] = Field(default_factory=lambda: list[str]())
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
    tool_names: list[str] = Field(default_factory=lambda: list[str]())
    tool_call_plan: list[AgentToolCallPlanItem] = Field(
        default_factory=lambda: list[AgentToolCallPlanItem]()
    )
    requires_clarification: bool = False
    clarification_question: str | None = None


###############################################################################
class DecisionTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    steps: list[str] = Field(default_factory=lambda: list[str]())


###############################################################################
class PolicyDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan: ExecutionPlan
    clarification: ClarificationRequest | None = None
    resolved_location: ResolvedLocation | None = None
    candidates: list[CapabilityCandidate] = Field(
        default_factory=lambda: list[CapabilityCandidate]()
    )
    trace: DecisionTrace = Field(default_factory=DecisionTrace)

    # -------------------------------------------------------------------------
    @property
    def selected_action(self) -> str:
        return self.plan.action_id

    # -------------------------------------------------------------------------
    @property
    def action_confidence(self) -> float:
        return 1.0

    # -------------------------------------------------------------------------
    @property
    def selected_tool_names(self) -> list[str]:
        return [self.plan.tool_id] if self.plan.tool_id else []

    # -------------------------------------------------------------------------
    @property
    def requires_location_resolution(self) -> bool:
        return self.resolved_location is None and self.plan.state in {
            "clarify",
            "map_search",
        }

    # -------------------------------------------------------------------------
    @property
    def requires_overlay_resolution(self) -> bool:
        return bool(self.plan.overlay_ids)

    # -------------------------------------------------------------------------
    @property
    def requires_external_source_query(self) -> bool:
        return self.plan.action_id == AgentAction.MAP_EXTERNAL_SOURCE_COMBINATION

    # -------------------------------------------------------------------------
    @property
    def requires_user_clarification(self) -> bool:
        return self.clarification is not None
