from __future__ import annotations

from server.domain.agent.decision import ExecutionPlan, ResolvedLocation
from server.domain.extraction.models import NormalizedAction
from server.domain.geographics import (
    LocationSearchRequest,
    PresentationPolicy,
    ViewportPolicy,
)


###############################################################################
class RequestBuilder:

    # -------------------------------------------------------------------------
    def build_location_search_request(
        self,
        plan: ExecutionPlan,
        location: ResolvedLocation,
    ) -> LocationSearchRequest:
        action = NormalizedAction(
            action_id=plan.action_id,
            action_label=plan.action_id,
            task_tags=[],
            action_tags=[],
        )
        overlays = list(plan.overlay_ids)
        return LocationSearchRequest(
            resolved_location=location,
            action_id=plan.action_id,
            time_mode="current",
            basemap_id=self.choose_basemap(plan),
            overlay_ids=overlays,
            viewport=self.build_viewport(location, action),
            presentation=self.build_presentation(overlays),
        )

    # -------------------------------------------------------------------------
    def choose_basemap(self, plan: ExecutionPlan) -> str:
        if plan.basemap_id:
            return plan.basemap_id
        if plan.action_id in {"weather", "air_quality"}:
            return "osm_dark"
        if plan.action_id in {"imagery", "satellite"}:
            return "gibs_satellite"
        if plan.action_id in {"solar", "terrain"}:
            return "osm_terrain"
        return "osm_default"

    # -------------------------------------------------------------------------
    def build_viewport(
        self,
        location: ResolvedLocation,
        action: NormalizedAction,
    ) -> ViewportPolicy:
        radius_m = 2500.0
        action_text = " ".join(
            [
                action.action_id,
                action.action_label,
                *action.task_tags,
                *action.action_tags,
            ]
        ).lower()
        if any(marker in action_text for marker in ("exact_address", "exact address", "address")):
            radius_m = 1000.0
        elif any(marker in action_text for marker in ("wide", "city", "city_level", "entire city")):
            radius_m = 25000.0
        elif any(marker in action_text for marker in ("region", "regional", "country", "island", "province")):
            radius_m = 100000.0
        elif action.action_id in {"traffic", "air_quality"}:
            radius_m = 4500.0
        return ViewportPolicy(
            center_latitude=location.latitude,
            center_longitude=location.longitude,
            radius_m=radius_m,
        )

    # -------------------------------------------------------------------------
    def build_presentation(self, overlays: list[str]) -> PresentationPolicy:
        high_contrast = any(
            marker in overlay
            for overlay in overlays
            for marker in ("air_quality", "traffic", "precipitation")
        )
        return PresentationPolicy(
            emphasize_overlays=bool(overlays),
            high_contrast=high_contrast,
            show_legend=bool(overlays),
        )
