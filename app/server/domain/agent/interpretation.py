"""Canonical, provider-neutral interpretation of one geospatial turn.

The parser is allowed to be probabilistic and model-shaped.  The rest of the
application is not: routing, argument construction, completion checks, and
conversation memory consume these small typed contracts instead of looking at
the user's prose independently.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from server.domain.agent.decision import ResolvedLocation

SpatialRelationship = Literal[
    "at",
    "in",
    "near",
    "around",
    "within_distance",
    "along",
    "north_of",
    "south_of",
    "east_of",
    "west_of",
    "visible_area",
    "here",
]

###############################################################################
def normalize_target_key(value: str) -> str:
    """Return the stable key shared by interpretation and location resolution.

    The geocoder folds accents and punctuation before comparing components.  A
    canonical target lookup must use the same identity function or a resolved
    ``São Paulo`` target can be lost when parser evidence is joined back to the
    resolver result.
    """

    normalized = unicodedata.normalize("NFKD", str(value or ""))
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_text = re.sub(r"(?<=[A-Za-z0-9])\.(?=[A-Za-z0-9])", "", ascii_text)
    ascii_text = re.sub(r"[^A-Za-z0-9]+", " ", ascii_text)
    return " ".join(ascii_text.casefold().split())


AnalysisScopeKind = Literal[
    "point",
    "bbox",
    "radius",
    "administrative_geometry",
    "feature_geometry",
    "viewport",
]
ResolutionStatus = Literal["resolved", "inherited", "ambiguous", "unresolved"]
CompletionStatus = Literal["pending", "satisfied", "failed", "not_applicable"]

###############################################################################
class CanonicalTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_id: str
    original_text: str
    entity_kind: str
    parent_target_ids: list[str] = Field(default_factory=list)
    resolved_location: ResolvedLocation | None = None
    geometry_ref: str | None = None
    resolution_status: ResolutionStatus = "unresolved"
    peer: bool = False

###############################################################################
class CanonicalSpatialConstraint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    relationship: SpatialRelationship
    target_id: str
    reference_target_id: str | None = None
    analysis_scope: AnalysisScopeKind
    distance_m: float | None = Field(default=None, gt=0.0)
    provenance: Literal["explicit", "parser", "inherited", "viewport"] = "parser"

###############################################################################
class CanonicalTemporalConstraints(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["current", "historical", "forecast", "none"] = "none"
    reference_time_iso: str | None = None
    start_time_iso: str | None = None
    end_time_iso: str | None = None
    granularity: str = "none"
    aggregation: str = "none"
    raw_text: str | None = None
    timezone: str = "UTC"
    timezone_source: Literal["client", "application", "utc"] = "utc"
    resolved_once: bool = False

###############################################################################
class CanonicalPresentation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["text", "map", "both"] = "map"
    geometry: list[str] = Field(default_factory=list)
    basemap_id: str | None = None
    viewport_operation: str = "auto"
    viewport_radius_m: float | None = Field(default=None, gt=0.0)
    viewport_tighten_relative_to_active: bool = False
    viewport_reason: str | None = None
    show_legend: bool = True

###############################################################################
class CompletionRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    required: bool = True
    status: CompletionStatus = "pending"
    target_id: str | None = None
    evidence_ref: str | None = None
    failure_code: str | None = None

###############################################################################
class CanonicalRequestInterpretation(BaseModel):
    """The single request interpretation consumed after parsing."""

    model_config = ConfigDict(extra="forbid")

    request_id: str
    interpretation_revision: int = Field(default=1, ge=1)
    relationship_to_previous_turn: str = "new_task"
    primary_intent: str
    operations: list[str] = Field(default_factory=list)
    targets: list[CanonicalTarget] = Field(
        default_factory=lambda: list[CanonicalTarget]()
    )
    spatial_constraints: list[CanonicalSpatialConstraint] = Field(
        default_factory=lambda: list[CanonicalSpatialConstraint]()
    )
    temporal_constraints: CanonicalTemporalConstraints = Field(
        default_factory=CanonicalTemporalConstraints
    )
    data_domains: list[str] = Field(default_factory=list)
    filters: dict[str, Any] = Field(default_factory=dict)
    presentation: CanonicalPresentation = Field(default_factory=CanonicalPresentation)
    map_required: bool = False
    ambiguities: list[str] = Field(default_factory=list)
    completion_requirements: list[CompletionRequirement] = Field(
        default_factory=lambda: list[CompletionRequirement]()
    )
    assumptions: list[str] = Field(default_factory=list)

    # -------------------------------------------------------------------------
    @property
    def primary_target(self) -> CanonicalTarget | None:
        """Return the first non-peer target without maintaining a second copy."""

        return next((target for target in self.targets if not target.peer), None)

    # -------------------------------------------------------------------------
    def target(self, target_id: str) -> CanonicalTarget | None:
        return next((item for item in self.targets if item.target_id == target_id), None)
