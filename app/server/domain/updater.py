from __future__ import annotations

from dataclasses import dataclass


@dataclass
class LayerAggregate:
    layer_id: str
    title: str
    abstract: str | None
    projections: set[str]
    source_urls: set[str]
    tile_matrix_sets: set[str]
