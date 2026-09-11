"""Strict model-facing map actions.

Only these typed actions cross the agent boundary.  Server-side services turn
them into renderer-safe ``MapSession`` descriptors; arbitrary MapLibre style
or source definitions are intentionally not representable here.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

###############################################################################
class MapActionBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str

###############################################################################
class SetBasemapAction(MapActionBase):
    action: Literal["set_basemap"]
    capability_id: str

###############################################################################
class AddEvidenceLayerAction(MapActionBase):
    action: Literal["add_evidence_layer"]
    evidence_ref: str
    capability_id: str
    visible: bool = True
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)

###############################################################################
class SetLayerVisibilityAction(MapActionBase):
    action: Literal["set_layer_visibility"]
    instance_id: str
    visible: bool

###############################################################################
class SetLayerOpacityAction(MapActionBase):
    action: Literal["set_layer_opacity"]
    instance_id: str
    opacity: float = Field(ge=0.0, le=1.0)

###############################################################################
class RemoveLayerAction(MapActionBase):
    action: Literal["remove_layer"]
    instance_id: str

###############################################################################
class KeepOnlyLayersAction(MapActionBase):
    action: Literal["keep_only_layers"]
    instance_ids: list[str] = Field(min_length=1, max_length=32)

###############################################################################
class SetViewportAction(MapActionBase):
    action: Literal["set_viewport"]
    strategy: Literal["fit_evidence", "fit_location", "preserve_current"]
    location_ref: str | None = None
    evidence_refs: list[str] = Field(default_factory=list, max_length=16)


MapAction = Annotated[
    SetBasemapAction
    | AddEvidenceLayerAction
    | SetLayerVisibilityAction
    | SetLayerOpacityAction
    | RemoveLayerAction
    | KeepOnlyLayersAction
    | SetViewportAction,
    Field(discriminator="action"),
]

###############################################################################
class MapPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_collection_revision: int = Field(ge=0)
    actions: list[MapAction] = Field(min_length=1, max_length=32)
