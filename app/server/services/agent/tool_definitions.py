"""Strict input models for the native model-facing tool primitives."""

from __future__ import annotations

from typing import Annotated, Any, Literal

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
    expected_location_type: (
        Literal[
            "address",
            "airport",
            "city",
            "country",
            "coordinates",
            "feature",
            "landmark",
            "poi",
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
            "administrative_geometry",
        ]
        | None
    ) = Field(
        default=None,
        description=(
            "Optional canonical target type. Use administrative_geometry for "
            "a state, province, region, county, or other administrative boundary. "
            "Use only the exact listed enum values; do not invent aliases."
        ),
    )
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
    cursor: str | None = Field(default=None, max_length=200)
    limit: int = Field(default=12, ge=1, le=50)


###############################################################################
class ProviderLayerDiscoveryInput(StrictToolInput):
    provider_id: str = Field(min_length=1, max_length=100)
    query: str | None = Field(default=None, max_length=300)
    cursor: str | None = Field(default=None, max_length=200)
    limit: int = Field(default=20, ge=1, le=50)
    refresh: bool = False


###############################################################################
class DescribeCapabilityInput(StrictToolInput):
    capability_id: str = Field(min_length=1, max_length=200)

###############################################################################
class ExecuteCapabilityInput(StrictToolInput):
    capability_id: str = Field(min_length=1, max_length=200)
    operation: str | None = Field(default=None, max_length=80)
    temporal_mode: str | None = Field(
        default=None,
        max_length=40,
        description=(
            "Optional route temporal hint. The server binds the effective "
            "temporal scope from the compiled route."
        ),
    )
    location_ref: str | None = Field(default=None, max_length=200)
    evidence_refs: list[str] = Field(default_factory=list, max_length=16)
    radius_m: float | None = Field(default=None, gt=0, le=1_000_000)
    bbox: list[float] | None = Field(default=None, min_length=4, max_length=4)
    start_time_iso: str | None = Field(default=None, max_length=80)
    end_time_iso: str | None = Field(default=None, max_length=80)
    filters: dict[str, Any] = Field(default_factory=dict)
    arguments: dict[str, Any] = Field(default_factory=dict)


###############################################################################
class ExecuteCapabilityToolInput(StrictToolInput):
    """Model intent for execution; geography and time remain server-owned."""

    capability_id: str = Field(min_length=1, max_length=200)
    operation: str | None = Field(default=None, max_length=80)
    location_ref: str | None = Field(default=None, max_length=200)
    evidence_refs: list[str] = Field(default_factory=list, max_length=16)
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
class AttributeFilterOperation(StrictToolInput):
    op: Literal["attribute_filter"]
    field: str = Field(min_length=1, max_length=200)
    operator: Literal["eq", "neq", "in", "contains", "gte", "lte"] = "eq"
    value: Any


###############################################################################
class TemporalFilterOperation(StrictToolInput):
    op: Literal["temporal_filter"]
    field: str = Field(default="timestamp", min_length=1, max_length=200)
    start: str | None = Field(default=None, max_length=80)
    end: str | None = Field(default=None, max_length=80)


###############################################################################
class SpatialFilterOperation(StrictToolInput):
    op: Literal["spatial_filter"]
    field: str = Field(default="geometry", min_length=1, max_length=200)
    center: list[float] = Field(min_length=2, max_length=2)
    radius_km: float = Field(gt=0, le=20_000)


###############################################################################
class SortOperation(StrictToolInput):
    op: Literal["sort"]
    field: str = Field(min_length=1, max_length=200)
    descending: bool = False


###############################################################################
class LimitOperation(StrictToolInput):
    op: Literal["limit"]
    value: int = Field(ge=1, le=10_000)


###############################################################################
class FieldProjectionOperation(StrictToolInput):
    op: Literal["field_projection"]
    fields: list[str] = Field(min_length=1, max_length=64)


###############################################################################
class AggregateOperation(StrictToolInput):
    op: Literal["aggregate"]
    field: str = Field(min_length=1, max_length=200)
    group_by: str = Field(min_length=1, max_length=200)


EvidenceOperation = Annotated[
    AttributeFilterOperation
    | TemporalFilterOperation
    | SpatialFilterOperation
    | SortOperation
    | LimitOperation
    | FieldProjectionOperation
    | AggregateOperation,
    Field(discriminator="op"),
]


###############################################################################
class TransformEvidenceInput(StrictToolInput):
    evidence_refs: list[str] = Field(min_length=1, max_length=8)
    operations: list[EvidenceOperation] = Field(min_length=1, max_length=8)

###############################################################################
class SearchConversationHistoryInput(StrictToolInput):
    """Bounded recall of original messages from the active conversation."""

    query: str = Field(min_length=1, max_length=300)
    before_turn_index: int | None = Field(default=None, ge=0)
    cursor: str | None = Field(default=None, max_length=200)
    limit: int = Field(default=8, ge=1, le=50)


# Keep the shorter spelling available to composition code while retaining a
# descriptive schema/class name in generated tool definitions.
HistorySearchInput = SearchConversationHistoryInput


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
    "DescribeCapabilityInput",
    "ExecuteCapabilityInput",
    "ExecuteCapabilityToolInput",
    "EvidenceOperation",
    "HistorySearchInput",
    "InspectEvidenceInput",
    "ProviderLayerDiscoveryInput",
    "ResolveLocationInput",
    "RouteRequestInput",
    "SearchConversationHistoryInput",
    "TransformEvidenceInput",
]
