from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class SearchPlan:
    selected_basemap_id: str
    selected_overlay_ids: list[str]
    compatibility_filters: list[str]
    selected_display_area: dict[str, Any]
    selected_location: dict[str, Any]
    confidence: float
    follow_up_reason: str | None


class SearchPlanner:
    def plan(
        self,
        *,
        intent: dict[str, Any],
        retrieval: dict[str, list[dict[str, object]]],
        manifests: dict[str, list[dict[str, Any]]],
    ) -> SearchPlan:
        basemap = self._select_basemap(intent=intent, retrieval=retrieval, manifests=manifests)
        overlays = self._select_overlays(intent=intent, retrieval=retrieval, manifests=manifests)
        location = intent.get("location") if isinstance(intent.get("location"), dict) else {}
        display_area = intent.get("display_area") if isinstance(intent.get("display_area"), dict) else {}
        planning = intent.get("planning") if isinstance(intent.get("planning"), dict) else {}
        return SearchPlan(
            selected_basemap_id=basemap,
            selected_overlay_ids=overlays,
            compatibility_filters=list(overlays),
            selected_display_area=display_area,
            selected_location=location,
            confidence=float(planning.get("confidence", 0.0) or 0.0),
            follow_up_reason=self._follow_up_reason(intent=intent, overlays=overlays),
        )

    def _select_basemap(
        self,
        *,
        intent: dict[str, Any],
        retrieval: dict[str, list[dict[str, object]]],
        manifests: dict[str, list[dict[str, Any]]],
    ) -> str:
        view = intent.get("view") if isinstance(intent.get("view"), dict) else {}
        map_type = str(view.get("map_type") or "auto")
        requested_satellite = map_type == "satellite"
        basemaps = retrieval.get("basemaps", [])
        manifest_lookup = {str(item.get("id")): item for item in manifests.get("basemaps", [])}
        ranked: list[tuple[float, str]] = []
        for candidate in basemaps:
            candidate_id = str(candidate.get("id") or "")
            if not candidate_id:
                continue
            item = manifest_lookup.get(candidate_id, {})
            score = float(candidate.get("score", 0.0) or 0.0)
            if requested_satellite and "sat" in str(item.get("name", "")).lower():
                score += 1.5
            ranked.append((score, candidate_id))
        if ranked:
            ranked.sort(key=lambda entry: entry[0], reverse=True)
            return ranked[0][1]
        return "osm_default"

    def _select_overlays(
        self,
        *,
        intent: dict[str, Any],
        retrieval: dict[str, list[dict[str, object]]],
        manifests: dict[str, list[dict[str, Any]]],
    ) -> list[str]:
        overlays_intent = intent.get("overlays") if isinstance(intent.get("overlays"), dict) else {}
        requested = [str(item) for item in overlays_intent.get("requested", []) if str(item).strip()]
        manifest_overlays = {str(item.get("id")): item for item in manifests.get("overlays", [])}
        selected: list[str] = []
        for overlay_id in requested:
            if overlay_id in manifest_overlays:
                selected.append(overlay_id)
        for candidate in retrieval.get("overlays", []):
            candidate_id = str(candidate.get("id") or "")
            if candidate_id in manifest_overlays and candidate_id not in selected:
                selected.append(candidate_id)
        return selected

    def _follow_up_reason(self, *, intent: dict[str, Any], overlays: list[str]) -> str | None:
        planning = intent.get("planning") if isinstance(intent.get("planning"), dict) else {}
        missing = [str(item).lower() for item in planning.get("missing_information", []) if str(item).strip()]
        if "location" in missing:
            return "ambiguous_location"
        if "display_area" in missing:
            return "missing_display_area"
        if planning.get("confidence") is not None and float(planning.get("confidence", 0.0)) < 0.35:
            return "low_confidence"
        if not overlays and intent.get("overlays"):
            return "unsupported_overlay"
        return None
