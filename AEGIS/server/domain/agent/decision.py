from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PlanState = Literal["clarify", "direct_tool", "map_search", "reject"]
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
    intent_id: str
    basemap_id: str | None = None
    overlay_ids: list[str] = Field(default_factory=list)
    tool_id: str | None = None

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
