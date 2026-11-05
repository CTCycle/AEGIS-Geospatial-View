"""Server-owned presentation contract and structured completion summary."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from server.domain.agent.capability_route import ObligationKind

# A fine-grained place (landmark, address, station...) must be framed at its
# own scale; a neighbourhood or district may fill a wider view.
FINE_LOCATION_TYPES = frozenset({
    "landmark", "poi", "address", "feature", "airport", "station", "street", "road",
})
LOCAL_LOCATION_TYPES = frozenset({"neighborhood", "district"})
MAX_FINE_VIEW_SPAN_DEGREES = 0.15
MAX_LOCAL_VIEW_SPAN_DEGREES = 0.6

MapState = Literal["rendered", "failed", "none"]
ObligationStatus = Literal["met", "unmet", "failed"]

###############################################################################
class ContractTarget(BaseModel):
    """One requested place the committed view must show."""

    model_config = ConfigDict(extra="forbid")

    ref: str = Field(min_length=1, max_length=200)
    label: str = Field(max_length=300)
    latitude: float = Field(ge=-90.0, le=90.0)
    longitude: float = Field(ge=-180.0, le=180.0)
    location_type: str | None = None

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
    def view_findings(self, viewport: list[float] | None) -> list[str]:
        """Targets outside the viewport, and fine places framed too coarsely."""

        if viewport is None or len(viewport) != 4:
            return []
        west, south, east, north = viewport
        span = max(abs(east - west), abs(north - south))
        out_of_view = [
            target.label or target.ref
            for target in self.targets
            if not (west <= target.longitude <= east and south <= target.latitude <= north)
        ]
        coarse = [
            target.label or target.ref
            for target in self.targets
            if target.location_type is not None
            and (
                (target.location_type in FINE_LOCATION_TYPES and span > MAX_FINE_VIEW_SPAN_DEGREES)
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
    def violations(self, viewport: list[float] | None) -> list[str]:
        return [*self.findings, *self.view_findings(viewport)]

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

###############################################################################
class CompletionSummary(BaseModel):
    """Run facts the final answer is generated from and checked against."""

    model_config = ConfigDict(extra="forbid")

    obligations: list[ObligationOutcome] = Field(
        default_factory=lambda: list[ObligationOutcome](), max_length=32
    )
    map_state: MapState = "none"
    presentation_findings: list[str] = Field(default_factory=lambda: list[str](), max_length=8)
    # (shown, total) per layer whose records were cut by a limit.
    truncations: list[tuple[int, int]] = Field(default_factory=lambda: list[tuple[int, int]](), max_length=8)

    # -------------------------------------------------------------------------
    def undelivered(self) -> list[ObligationOutcome]:
        return [item for item in self.obligations if item.status != "met"]

    # -------------------------------------------------------------------------
    def disclosure(self) -> str:
        """Plain sentences for everything the user did not get."""

        sentences: list[str] = []
        if self.map_state == "failed":
            sentences.append("The map could not be confirmed in the browser, so it is not shown as requested.")
        sentences.extend(
            f"Map check: {finding}." for finding in self.presentation_findings
        )
        undelivered = [item.label or item.obligation_id for item in self.undelivered()]
        if undelivered:
            sentences.append("Not delivered: " + "; ".join(undelivered) + ".")
        for shown, total in self.truncations:
            sentences.append(f"The map layer shows only {shown} of {total} records.")
        return " ".join(sentences)

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
            "truncated_layers": [f"{shown} of {total}" for shown, total in self.truncations],
        }
