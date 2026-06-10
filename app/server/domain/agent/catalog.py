from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TypedDict

CATALOG_PAGE_LIMIT = 50


@dataclass(frozen=True)
class CapabilityCatalogFilter:
    query: str | None = None
    category: str | None = None
    geometry_type: str | None = None
    bbox: list[float] | None = None
    limit: int = CATALOG_PAGE_LIMIT
    cursor: str | None = None


class GeospatialCapabilityExecutionResult(TypedDict, total=False):
    ok: bool
    operation: str
    capability_id: str
    arguments: dict[str, Any]
    map_session: dict[str, Any] | None
    direct_result: dict[str, Any] | None
    capability_selection: dict[str, Any] | None
    observations: list[dict[str, Any]]
