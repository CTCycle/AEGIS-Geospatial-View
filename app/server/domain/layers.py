from __future__ import annotations

from pydantic import BaseModel, Field

###############################################################################
class LayerProviderEntry(BaseModel):
    layer_id: str
    title: str
    abstract: str | None = None
    name: str | None = None
    provider: str | None = None
    label: str | None = None
    aliases: tuple[str, ...] = Field(default_factory=tuple)
    provider_name: str | None = None
    resolution_m: float | None = None
    projections: set[str] = Field(default_factory=lambda: set[str]())
    source_urls: set[str] = Field(default_factory=lambda: set[str]())
    tile_matrix_sets: set[str] = Field(default_factory=lambda: set[str]())
