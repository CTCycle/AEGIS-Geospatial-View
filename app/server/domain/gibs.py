from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LayerMetadata:
    name: str
    supported_crs: frozenset[str]
    formats: frozenset[str]
    time_extent: str | None


@dataclass(frozen=True)
class Capabilities:
    layers: dict[str, LayerMetadata]
    supported_formats: frozenset[str]
    retrieved_at: float
