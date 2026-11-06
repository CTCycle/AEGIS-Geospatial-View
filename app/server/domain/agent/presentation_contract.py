"""Server-owned presentation contract and structured completion summary."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from server.domain.agent.capability_route import ObligationKind

# A fine-grained place (landmark, address, station...) must be framed at its
# own scale; a neighbourhood or district may fill a wider view.
FINE_LOCATION_TYPES = frozenset({
    "landmark", "poi", "address", "feature", "airport", "station", "street", "road",
    "attraction", "monument", "building",
})
LOCAL_LOCATION_TYPES = frozenset({"neighborhood", "district"})
# Wide enough for a street-level fit on a landscape map (the long side of the
# view), narrow enough that a city-scale view of a landmark never passes.
MAX_FINE_VIEW_SPAN_DEGREES = 0.06
# Width of the box a fine place is framed in; the map widens it to its aspect.
FINE_PLACE_FRAME_DEGREES = 0.01
# Geocoders name the same kind of place differently; a result whose own extent
# is this small is fine-grained whatever its type is called.
FINE_PLACE_EXTENT_DEGREES = 0.02
MAX_LOCAL_VIEW_SPAN_DEGREES = 0.6
# Scopes whose centre point says nothing about what must be visible.
AREA_LOCATION_TYPES = frozenset({
    "country", "state", "province", "region", "macro_region", "continent",
    "ocean", "sea", "viewport", "global", "world",
})
MIN_RESULTS_IN_VIEW = 0.5
# A target spanning at least this much longitude is the whole globe: no
# viewport can contain it, so it never counts as out of view.
GLOBAL_EXTENT_SPAN_DEGREES = 340.0

MapState = Literal["rendered", "failed", "none"]
# "unsupported": the only evidence is imagery, which carries no records to analyse.
ObligationStatus = Literal["met", "unmet", "failed", "unsupported"]

###############################################################################
def substitution_sentence(rejected: str, coverage: str, alternative: str) -> str:
    return f"{rejected} only covers {coverage or 'a limited area'}, so {alternative} is shown instead."

###############################################################################
def is_fine_place(location_type: str | None, bbox: list[float] | None) -> bool:
    """Whether a place must be framed at its own scale (landmark, address...)."""

    if location_type in FINE_LOCATION_TYPES:
        return True
    return (
        bbox is not None
        and location_type not in AREA_LOCATION_TYPES
        and max(bbox[2] - bbox[0], bbox[3] - bbox[1]) <= FINE_PLACE_EXTENT_DEGREES
    )

###############################################################################
class ContractTarget(BaseModel):
    """One requested place the committed view must show."""

    model_config = ConfigDict(extra="forbid")

    ref: str = Field(min_length=1, max_length=200)
    label: str = Field(max_length=300)
    latitude: float = Field(ge=-90.0, le=90.0)
    longitude: float = Field(ge=-180.0, le=180.0)
    location_type: str | None = None
    bbox: list[float] | None = Field(default=None, min_length=4, max_length=4)

    # -------------------------------------------------------------------------
    @property
    def is_fine(self) -> bool:
        return is_fine_place(self.location_type, self.bbox)

    # -------------------------------------------------------------------------
    @property
    def is_global(self) -> bool:
        return self.bbox is not None and self.bbox[2] - self.bbox[0] >= GLOBAL_EXTENT_SPAN_DEGREES

###############################################################################
class PresentationContract(BaseModel):
    """What the browser view must show for the request to count as presented.

    Built from the presentation obligations when a candidate is prepared:
    ``findings`` are the candidate-time verdicts (provenance, layer time,
    requested transform, labelled values) and ``targets`` are checked against
    the browser viewport once it is acknowledged.
    """

    model_config = ConfigDict(extra="forbid")

    targets: list[ContractTarget] = Field(default_factory=lambda: list[ContractTarget](), max_length=16)
    findings: list[str] = Field(default_factory=lambda: list[str](), max_length=8)

    # -------------------------------------------------------------------------
    def view_findings(
        self, viewport: list[float] | None, results_in_viewport: float | None = None
    ) -> list[str]:
        """Targets outside the viewport, and fine places framed too coarsely.

        A point place must have its centre in view. An area or global scope has
        no meaningful centre, so it is judged by the share of the rendered
        result extent in view (unknown means no evidence of a failure).
        """

        if viewport is None or len(viewport) != 4:
            return []
        west, south, east, north = viewport
        span = max(abs(east - west), abs(north - south))
        out_of_view = [
            target.label or target.ref
            for target in self.targets
            if not target.is_global
            and (
                (results_in_viewport is not None and results_in_viewport < MIN_RESULTS_IN_VIEW)
                if target.location_type in AREA_LOCATION_TYPES
                else not (west <= target.longitude <= east and south <= target.latitude <= north)
            )
        ]
        coarse = [
            target.label or target.ref
            for target in self.targets
            if (
                (target.is_fine and span > MAX_FINE_VIEW_SPAN_DEGREES)
                or (target.location_type in LOCAL_LOCATION_TYPES and span > MAX_LOCAL_VIEW_SPAN_DEGREES)
            )
        ]
        findings: list[str] = []
        if out_of_view:
            findings.append("requested places outside the map view: " + ", ".join(out_of_view))
        if coarse:
            findings.append(
                "map view too wide for "
                + ", ".join(coarse)
                + f" (shows {span:.2f} degrees); zoom to the place itself"
            )
        return findings

    # -------------------------------------------------------------------------
    def violations(
        self, viewport: list[float] | None, results_in_viewport: float | None = None
    ) -> list[str]:
        return [*self.findings, *self.view_findings(viewport, results_in_viewport)]

###############################################################################
class ObligationOutcome(BaseModel):
    """Verified status of one request obligation."""

    model_config = ConfigDict(extra="forbid")

    obligation_id: str = Field(max_length=200)
    kind: ObligationKind
    label: str = Field(default="", max_length=200)
    status: ObligationStatus
    evidence_ref: str | None = None
    values: list[str] = Field(default_factory=lambda: list[str](), max_length=8)
    # Spellings the answer must use to name what this obligation asked for.
    answer_must_name: list[str] = Field(default_factory=lambda: list[str](), max_length=4)
    # Figures an analysis answer must cite: one group per compared target (a
    # figure of each group, or their difference) or a single group.
    cite_groups: list[list[float]] = Field(default_factory=lambda: list[list[float]]())

###############################################################################
class CompletionSummary(BaseModel):
    """Run facts the final answer is generated from and checked against."""

    model_config = ConfigDict(extra="forbid")

    obligations: list[ObligationOutcome] = Field(
        default_factory=lambda: list[ObligationOutcome](), max_length=32
    )
    map_state: MapState = "none"
    presentation_findings: list[str] = Field(default_factory=lambda: list[str](), max_length=8)
    # A rejected source replaced by a covering one that then ran.
    # (rejected source, its coverage, covering source shown instead).
    substitutions: list[tuple[str, str, str]] = Field(
        default_factory=lambda: list[tuple[str, str, str]](), max_length=4
    )
    # (shown, total) per layer whose records were cut by a limit.
    truncations: list[tuple[int, int]] = Field(default_factory=lambda: list[tuple[int, int]](), max_length=8)

    # -------------------------------------------------------------------------
    def undelivered(self) -> list[ObligationOutcome]:
        return [item for item in self.obligations if item.status != "met"]

    # -------------------------------------------------------------------------
    def disclosure(self) -> str:
        """Plain sentences for everything the user did not get."""

        sentences: list[str] = [substitution_sentence(*item) for item in self.substitutions]
        if self.map_state == "failed":
            sentences.append("The map could not be confirmed in the browser, so it is not shown as requested.")
        sentences.extend(
            f"Map check: {finding}." for finding in self.presentation_findings
        )
        unsupported = [item.label or item.obligation_id for item in self.obligations if item.status == "unsupported"]
        if unsupported:
            sentences.append(
                "Only map imagery was available, which has no point or numeric records, so "
                + "; ".join(unsupported)
                + " could not be computed from records; the imagery is shown instead."
            )
        undelivered = [
            item.label or item.obligation_id for item in self.undelivered() if item.status != "unsupported"
        ]
        if undelivered:
            sentences.append("Not delivered: " + "; ".join(undelivered) + ".")
        for shown, total in self.truncations:
            sentences.append(f"The map layer shows only {shown} of {total} records.")
        return " ".join(sentences)

    # -------------------------------------------------------------------------
    def value_lines(self) -> str:
        """The figures of every delivered data and analysis obligation."""

        return "\n".join(
            f"- {item.label}: {', '.join(item.values)}"
            for item in self.obligations
            if item.values
        )

    # -------------------------------------------------------------------------
    def model_view(self) -> dict[str, object]:
        """Compact form handed to the final-answer step."""

        return {
            "map_state": self.map_state,
            "obligations": [
                {
                    key: value
                    for key, value in {
                        "id": item.obligation_id,
                        "status": item.status,
                        "evidence_ref": item.evidence_ref,
                        "values": item.values,
                    }.items()
                    if value
                }
                for item in self.obligations
            ],
            "presentation_findings": self.presentation_findings,
            "substitutions": [substitution_sentence(*item) for item in self.substitutions],
            "truncated_layers": [f"{shown} of {total}" for shown, total in self.truncations],
        }
