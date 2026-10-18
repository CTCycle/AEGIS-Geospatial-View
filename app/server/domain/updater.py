from __future__ import annotations

from pydantic import BaseModel, Field

###############################################################################
class LayerAggregate(BaseModel):
    layer_id: str
    title: str
    abstract: str | None = None
    projections: set[str] = Field(default_factory=lambda: set[str]())
    source_urls: set[str] = Field(default_factory=lambda: set[str]())
    tile_matrix_sets: set[str] = Field(default_factory=lambda: set[str]())
