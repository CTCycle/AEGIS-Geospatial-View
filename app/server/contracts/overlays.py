"""Typed overlay mutation contracts for the native map state."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


OverlayAction = Literal["add", "remove", "keep_only", "show", "hide", "update"]
OverlayScopeKind = Literal["global", "current_view", "location"]
OverlayVisibility = Literal["any", "visible", "hidden"]


class OverlaySelector(BaseModel):
    """Independent selectors for capabilities and rendered instances."""

    model_config = ConfigDict(extra="forbid")

    instance_ids: list[str] = Field(default_factory=list)
    capability_ids: list[str] = Field(default_factory=list)
    concepts: list[str] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)
    providers: list[str] = Field(default_factory=list)
    overlay_types: list[str] = Field(default_factory=list)
    rendering_modes: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    visibility: OverlayVisibility = "any"


class OverlayScope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: OverlayScopeKind = "global"
    location: dict[str, Any] | None = None
    label: str | None = None


class OverlayPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    opacity: float | None = Field(default=None, ge=0.0, le=1.0)
    time: str | None = None
    style: str | None = None
    format: str | None = None


class OverlayStateReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    collection_id: str = "active-map"
    revision: int = Field(default=0, ge=0)


class OverlayCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: OverlayAction
    selector: OverlaySelector = Field(default_factory=OverlaySelector)
    scope: OverlayScope = Field(default_factory=OverlayScope)
    patch: OverlayPatch = Field(default_factory=OverlayPatch)
    state_reference: OverlayStateReference = Field(
        default_factory=OverlayStateReference
    )


__all__ = [
    "OverlayAction",
    "OverlayCommand",
    "OverlayPatch",
    "OverlayScope",
    "OverlayScopeKind",
    "OverlaySelector",
    "OverlayStateReference",
    "OverlayVisibility",
]
