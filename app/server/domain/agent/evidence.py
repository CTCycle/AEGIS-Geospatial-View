"""Contracts for bounded, conversation-scoped agent evidence."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

EvidenceStatus = Literal["available", "partial", "valid_empty", "failed", "superseded"]
EvidenceKind = Literal[
    "location",
    "capability_result",
    "provider_layer_descriptor",
    "vector",
    "tabular",
    "raster_descriptor",
    "derived",
    "diagnostic",
]


###############################################################################
class AgentEvidenceSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    kind: EvidenceKind
    media_type: str
    status: EvidenceStatus
    summary: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)
    parent_evidence_ids: list[str] = Field(default_factory=list)
    byte_size: int = Field(default=0, ge=0)
    sha256: str | None = None
    map_eligibility: Literal["renderable", "not_renderable", "unknown"] = "unknown"


###############################################################################
class AgentEvidenceEnvelope(BaseModel):
    """Normalized result shape used by map preparation and evidence tools."""

    model_config = ConfigDict(extra="forbid")

    ok: bool
    status: EvidenceStatus | Literal["error"]
    evidence_ref: str | None = None
    summary: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)
    map_eligibility: Literal["renderable", "not_renderable", "unknown"] = "unknown"
    # Server-only bounded payload used to build a renderable evidence layer.
    # It never enters model-facing observation messages.
    payload: Any = None
    error: dict[str, Any] | None = None
    pagination: dict[str, Any] | None = None
    state_changes: list[dict[str, Any]] = Field(
        default_factory=lambda: list[dict[str, Any]]()
    )


__all__ = [
    "AgentEvidenceEnvelope",
    "AgentEvidenceSummary",
    "EvidenceKind",
    "EvidenceStatus",
]
