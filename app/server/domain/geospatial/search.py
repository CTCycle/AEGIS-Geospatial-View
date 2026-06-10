from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


###############################################################################
@dataclass(frozen=True)
class IndexedFeature:
    id: str
    label: str
    category: str | None = None
    source: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


###############################################################################
@dataclass(frozen=True)
class SearchIndex:
    features: list[IndexedFeature]
    terms: dict[str, list[str]]
