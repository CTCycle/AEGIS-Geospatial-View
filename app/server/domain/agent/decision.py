from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, field_validator

from server.common.time import utc_now

"""Location-resolution value objects used by the native agent boundary."""

# Hierarchy source of the names a reverse geocode gave a coordinate location.
REVERSE_GEOCODER_SOURCE = "reverse_geocoder"

# A clarification offers 2-5 short answer choices, or none when open-ended.
CLARIFICATION_MIN_OPTIONS = 2
CLARIFICATION_MAX_OPTIONS = 5
CLARIFICATION_OPTION_MAX_CHARS = 100

###############################################################################
def normalize_clarification_options(values: Iterable[object] | None) -> list[str]:
    """Return distinct, trimmed answer choices, or none when fewer than two."""

    options: list[str] = []
    seen: set[str] = set()
    for value in values or ():
        label = " ".join(str(value).split())
        key = label.casefold()
        if not label or len(label) > CLARIFICATION_OPTION_MAX_CHARS or key in seen:
            continue
        seen.add(key)
        options.append(label)
    if len(options) < CLARIFICATION_MIN_OPTIONS:
        return []
    return options[:CLARIFICATION_MAX_OPTIONS]

###############################################################################
class ClarificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str
    reason: str
    missing_fields: list[str] = Field(default_factory=lambda: list[str]())
    options: list[str] = Field(default_factory=lambda: list[str]())

    @field_validator("options")
    @classmethod
    def _normalize_options(cls, value: list[str]) -> list[str]:
        return normalize_clarification_options(value)

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
    # Wikidata entity of the geocoded place, used for place-fact lookups.
    wikidata_id: str | None = Field(default=None, pattern=r"^Q\d+$")
    provenance: LocationResolutionProvenance | None = None
    hierarchy: LocationHierarchy | None = None

    # -------------------------------------------------------------------------
    def reverse_geocoded_name(self) -> str | None:
        """The place a reverse geocode named here, e.g. "Lugano, Ticino, Switzerland"."""

        parents = self.hierarchy.parents if self.hierarchy is not None else []
        names = [
            item.canonical_label
            for item in parents
            if item.source == REVERSE_GEOCODER_SOURCE and item.canonical_label
        ]
        return ", ".join(names) or None
