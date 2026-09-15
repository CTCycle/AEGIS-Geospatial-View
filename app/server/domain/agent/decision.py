from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

from server.common.time import utc_now

"""Location-resolution value objects used by the native agent boundary."""

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
