from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class SearchPlan:
    selected_basemap_id: str
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
        basemap = self._select_basemap(intent=intent, retrieval=retrieval, manifests=manifests)
        overlays = self._select_overlays(intent=intent, retrieval=retrieval, manifests=manifests)
        location = intent.get("location") if isinstance(intent.get("location"), dict) else {}
        planning = intent.get("planning") if isinstance(intent.get("planning"), dict) else {}
        fallback_mode = str(planning.get("fallback_mode") or "none")
        should_execute = bool(planning.get("should_execute_search", True))
        is_partial = bool(location.get("is_partial", False))
        if is_partial and fallback_mode == "none":
            fallback_mode = "partial_location"
            should_execute = False
        return SearchPlan(
            selected_basemap_id=basemap,
            selected_overlay_ids=overlays,
            compatibility_filters=list(overlays),
            selected_location=location,
            confidence=float(planning.get("confidence", 0.0) or 0.0),
            follow_up_reason=self._follow_up_reason(intent=intent, overlays=overlays),
            should_execute=should_execute,
            fallback_mode=fallback_mode,
            clarification_needed=not should_execute,
            preview_location=location if is_partial else None,
            preview_basemap_id="osm_default" if is_partial else None,
            preview_overlay_ids=[] if is_partial else None,
        )

    def _select_basemap(
        self,
        *,
        intent: dict[str, Any],
        retrieval: dict[str, list[dict[str, object]]],
        manifests: dict[str, list[dict[str, Any]]],
    ) -> str:
        preferences = intent.get("map_preferences") if isinstance(intent.get("map_preferences"), dict) else {}
        map_type = str(preferences.get("map_type") or "auto")
        basemaps = retrieval.get("basemaps", [])
        manifest_lookup = {str(item.get("id")): item for item in manifests.get("basemaps", [])}
        ranked: list[tuple[float, str]] = []
        for candidate in basemaps:
            candidate_id = str(candidate.get("id") or "")
            if not candidate_id:
                continue
            item = manifest_lookup.get(candidate_id, {})
            score = float(candidate.get("score", 0.0) or 0.0)
            score += self._map_type_bonus(map_type=map_type, candidate=item)
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
        prefs = intent.get("map_preferences") if isinstance(intent.get("map_preferences"), dict) else {}
        requested = [str(item) for item in prefs.get("overlay_candidates", []) if str(item).strip()]
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
        if not overlays and intent.get("map_preferences"):
            return "unsupported_overlay"
        return None

    def _map_type_bonus(self, *, map_type: str, candidate: dict[str, Any]) -> float:
        metadata = candidate.get("metadata") if isinstance(candidate.get("metadata"), dict) else {}
        tags = metadata.get("style_tags") if isinstance(metadata.get("style_tags"), list) else []
        joined = " ".join(str(tag).lower() for tag in tags)
        text = f"{candidate.get('name', '')} {candidate.get('description', '')}".lower()
        bucket = f"{joined} {text}"
        if map_type == "satellite" and ("satellite" in bucket or "imagery" in bucket):
            return 1.4
        if map_type == "terrain" and ("terrain" in bucket or "topo" in bucket):
            return 1.2
        if map_type == "dark" and "dark" in bucket:
            return 1.2
        if map_type == "light" and "light" in bucket:
            return 1.0
        if map_type == "street" and ("street" in bucket or "road" in bucket or "osm" in bucket):
            return 1.1
        return 0.0
