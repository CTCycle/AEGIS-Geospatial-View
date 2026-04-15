from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class SearchPlan:
    selected_basemap_id: str | None
    selected_overlay_ids: list[str]
    compatibility_filters: list[str]
    selected_location: dict[str, Any]
    confidence: float
    follow_up_reason: str | None
    should_execute: bool = True
    fallback_mode: str = "none"
    clarification_needed: bool = False
    preview_location: dict[str, Any] | None = None
    preview_basemap_id: str | None = None
    preview_overlay_ids: list[str] | None = None
    preview_map_session: dict[str, Any] | None = None


class SearchPlanner:
    def plan(
        self,
        *,
        intent: dict[str, Any],
        retrieval: dict[str, list[dict[str, object]]],
        manifests: dict[str, list[dict[str, Any]]],
    ) -> SearchPlan:
        location = intent.get("location") if isinstance(intent.get("location"), dict) else {}
        has_coordinates = (
            isinstance(intent.get("coordinates"), dict)
            and intent["coordinates"].get("latitude") is not None
            and intent["coordinates"].get("longitude") is not None
        )
        has_location = any([location.get("address"), location.get("city"), location.get("country"), has_coordinates])
        basemap = retrieval.get("basemaps", [])
        overlays = retrieval.get("overlays", [])
        selected_basemap = str(basemap[0].get("id")) if basemap else "osm_default"
        selected_overlays = [str(item.get("id")) for item in overlays[:5] if item.get("id")]
        should_execute = has_location
        fallback_mode = "none" if should_execute else "missing_location"
        return SearchPlan(
            selected_basemap_id=selected_basemap,
            selected_overlay_ids=selected_overlays,
            compatibility_filters=list(selected_overlays),
            selected_location=location,
            confidence=float(intent.get("certainty") or 0.0),
            follow_up_reason=None if should_execute else "ambiguous_location",
            should_execute=should_execute,
            fallback_mode=fallback_mode,
            clarification_needed=not should_execute,
        )
