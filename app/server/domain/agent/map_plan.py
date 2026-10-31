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

###############################################################################
class SetBasemapAction(MapActionBase):
    action: Literal["set_basemap"]
    capability_id: str

###############################################################################
class ValueEncoding(MapActionBase):
    mode: Literal["graduated", "heatmap"]
    field: str = Field(min_length=1, max_length=200)


###############################################################################
class AddEvidenceLayerAction(MapActionBase):
    action: Literal["add_evidence_layer"]
    evidence_ref: str
    capability_id: str
    value_encoding: ValueEncoding | None = None
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
    strategy: Literal[
        "fit_evidence", "fit_location", "preserve_current", "zoom_in", "zoom_out", "pan"
    ]
    location_ref: str | None = None
    evidence_refs: list[str] = Field(
        default_factory=lambda: list[str](), max_length=16
    )
    # zoom_in/zoom_out/pan move the view the user sees; the server computes
    # the geometry, the model only chooses how far and which way.
    steps: int = Field(
        default=1,
        ge=1,
        le=4,
        description="zoom_in/zoom_out: zoom levels (2 or more for 'a lot'); pan: half-view moves.",
    )
    direction: Literal["north", "south", "east", "west"] | None = Field(
        default=None, description="Required for pan."
    )
    anchor: Literal["current_view", "location"] = Field(
        default="current_view",
        description="zoom centre: the current view, or the map's place (its city centre).",
    )


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
