from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from AEGIS.server.domain.agent.decision import ResolvedLocation

TimeMode = Literal["current", "historical", "forecast"]

###############################################################################
class ViewportPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    center_latitude: float = Field(..., ge=-90.0, le=90.0)
    center_longitude: float = Field(..., ge=-180.0, le=180.0)
    radius_m: float = Field(default=2500.0, gt=0)
    bbox: list[float] | None = None

###############################################################################
class PresentationPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    emphasize_overlays: bool = False
    high_contrast: bool = False
    show_legend: bool = True

###############################################################################
class LocationSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resolved_location: ResolvedLocation
    intent_id: str
    time_mode: TimeMode = "current"
    basemap_id: str
    overlay_ids: list[str] = Field(default_factory=list)
    viewport: ViewportPolicy
    presentation: PresentationPolicy = Field(default_factory=PresentationPolicy)

###############################################################################
class MapSession(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    resolved_location: ResolvedLocation
    basemap_id: str
    overlay_ids: list[str] = Field(default_factory=list)
    viewport: ViewportPolicy
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    payload: dict[str, object] = Field(default_factory=dict)


class SearchByLocationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status_message: str
    map_session: MapSession

###############################################################################
class GeospatialCatalogResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capabilities: list[dict[str, object]] = Field(default_factory=list)
