from __future__ import annotations

from pydantic import BaseModel, Field


class LayerMetadata(BaseModel):
    layer_id: str
    title: str
    abstract: str | None = None
    projections: set[str] = Field(default_factory=set)
    source_urls: set[str] = Field(default_factory=set)
    tile_matrix_sets: set[str] = Field(default_factory=set)


class Capabilities(BaseModel):
    layers: list[LayerMetadata] = Field(default_factory=list)
