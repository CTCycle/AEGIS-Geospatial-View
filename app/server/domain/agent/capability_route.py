"""Typed routing and working-state contracts for the native agent loop.

The legacy agent keeps its parser and planner contracts for now.  These models
are deliberately independent of those services so the native-v2 path can be
introduced and tested without making the model responsible for provider or
MapLibre implementation details.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from server.contracts.geospatial import MapSession
from server.domain.agent.decision import ResolvedLocation
from server.domain.agent.interpretation import CanonicalRequestInterpretation
from server.domain.agent.tool_result import ToolResult


###############################################################################
class CapabilityDomain(StrEnum):
    CONVERSATION = "conversation"
    PLACE_SEARCH = "place_search"
    DATA_RETRIEVAL = "data_retrieval"
    SPATIAL_ANALYSIS = "spatial_analysis"
    ROUTING = "routing"
    MAP_RENDERING = "map_rendering"
    MAP_STATE = "map_state"
    PROVIDER_DISCOVERY = "provider_discovery"
    MIXED = "mixed"


###############################################################################
class CapabilityRoute(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary_domain: CapabilityDomain
    secondary_domains: list[CapabilityDomain] = Field(default_factory=list, max_length=3)
    task_mode: Literal["answer", "execute", "clarify"]
    presentation: Literal["text", "map", "both"]
    requires_location: bool
    capability_queries: list[str] = Field(default_factory=list, max_length=4)
    explicit_capability_ids: list[str] = Field(default_factory=list, max_length=8)
    clarification_question: str | None = Field(default=None, max_length=500)


###############################################################################
class AgentPhase(StrEnum):
    RECEIVE_REQUEST = "receive_request"
    ROUTE_REQUEST = "route_request"
    BUILD_TOOL_CONTEXT = "build_tool_context"
    MODEL_STEP = "model_step"
    VALIDATE_ACTION = "validate_action"
    EXECUTE_TOOL = "execute_tool"
    NORMALIZE_RESULT = "normalize_result"
    UPDATE_STATE = "update_state"
    EVALUATE_STOP = "evaluate_stop"
    AWAIT_RENDER = "await_render"
    FINALIZE = "finalize"
    FAILED = "failed"


###############################################################################
class AgentState(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    request_id: str
    conversation_id: str
    phase: AgentPhase
    user_message: str
    route: CapabilityRoute | None = None
    capability_ids: list[str] = Field(default_factory=list)
    location_refs: dict[str, ResolvedLocation] = Field(default_factory=dict)
    evidence_refs: list[str] = Field(default_factory=list)
    active_map_session: MapSession | None = None
    prepared_map_session: MapSession | None = None
    canonical_request: CanonicalRequestInterpretation | None = None
    tool_results: list[ToolResult] = Field(default_factory=list)
    successful_fingerprints: dict[str, ToolResult] = Field(default_factory=dict)
    failed_fingerprints: dict[str, int] = Field(default_factory=dict)
    consecutive_tool_failures: int = Field(default=0, ge=0)
    route_corrections: int = Field(default=0, ge=0)
    validation_corrections: int = Field(default=0, ge=0)
    model_calls: int = Field(default=0, ge=0)
    tool_calls: int = Field(default=0, ge=0)
    transitions: int = Field(default=0, ge=0)
    termination_reason: str | None = None
