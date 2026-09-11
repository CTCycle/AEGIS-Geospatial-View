"""Strict input models for the native-v2 model-facing tool primitives."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from server.domain.agent.capability_route import CapabilityRoute
from server.domain.agent.map_plan import MapAction

###############################################################################
class StrictToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

###############################################################################
class ResolveLocationInput(StrictToolInput):
    query: str | None = Field(default=None, min_length=1, max_length=300)
    target_id: str | None = Field(default=None, min_length=1, max_length=200)
    expected_location_type: str | None = Field(default=None, max_length=80)
    candidate_id: str | None = Field(default=None, max_length=200)

    # -------------------------------------------------------------------------
    @model_validator(mode="after")
    def require_query_or_target(self) -> "ResolveLocationInput":
        if not self.query and not self.target_id:
            raise ValueError("Either query or target_id is required.")
        return self

###############################################################################
class CapabilityDiscoveryInput(StrictToolInput):
    query: str | None = Field(default=None, max_length=300)
    capability_ids: list[str] = Field(default_factory=list, max_length=8)
    provider_id: str | None = Field(default=None, max_length=100)
    include_provider_layers: bool = False
    cursor: str | None = Field(default=None, max_length=200)
    limit: int = Field(default=12, ge=1, le=25)

###############################################################################
class ExecuteCapabilityInput(StrictToolInput):
    capability_id: str = Field(min_length=1, max_length=200)
    operation: str | None = Field(default=None, max_length=80)
    location_ref: str | None = Field(default=None, max_length=200)
    evidence_refs: list[str] = Field(default_factory=list, max_length=16)
    radius_m: float | None = Field(default=None, gt=0, le=1_000_000)
    bbox: list[float] | None = Field(default=None, min_length=4, max_length=4)
    start_time_iso: str | None = Field(default=None, max_length=80)
    end_time_iso: str | None = Field(default=None, max_length=80)
    filters: dict[str, Any] = Field(default_factory=dict)
    arguments: dict[str, Any] = Field(default_factory=dict)

###############################################################################
class InspectEvidenceInput(StrictToolInput):
    evidence_ref: str = Field(min_length=1, max_length=200)
    view: str = Field(pattern="^(metadata|schema|sample|statistics|page)$")
    fields: list[str] = Field(default_factory=list, max_length=32)
    cursor: str | None = Field(default=None, max_length=200)
    limit: int = Field(default=20, ge=1, le=100)

###############################################################################
class TransformEvidenceInput(StrictToolInput):
    evidence_refs: list[str] = Field(min_length=1, max_length=8)
    operations: list[dict[str, Any]] = Field(min_length=1, max_length=8)

###############################################################################
class ApplyMapPlanInput(StrictToolInput):
    expected_collection_revision: int = Field(ge=0)
    actions: list[MapAction] = Field(min_length=1, max_length=32)

###############################################################################
class RouteRequestInput(CapabilityRoute):
    """Named alias used when registering the internal bootstrap tool."""


__all__ = [
    "ApplyMapPlanInput",
    "CapabilityDiscoveryInput",
    "ExecuteCapabilityInput",
    "InspectEvidenceInput",
    "ResolveLocationInput",
    "RouteRequestInput",
    "TransformEvidenceInput",
]
