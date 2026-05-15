from __future__ import annotations

from server.domain.agent.decision import ExecutionPlan, ResolvedLocation
from server.domain.extraction.models import NormalizedIntent
from server.domain.geographics import (
    LocationSearchRequest,
    PresentationPolicy,
    ViewportPolicy,
)


class RequestBuilder:
    def build_location_search_request(
        self,
        plan: ExecutionPlan,
        location: ResolvedLocation,
    ) -> LocationSearchRequest:
        intent = NormalizedIntent(
            intent_id=plan.intent_id,
            intent_label=plan.intent_id,
            task_tags=[],
            intent_tags=[],
        )
        overlays = list(plan.overlay_ids)
        return LocationSearchRequest(
            resolved_location=location,
            intent_id=plan.intent_id,
            time_mode="current",
            basemap_id=self.choose_basemap(plan),
            overlay_ids=overlays,
            viewport=self.build_viewport(location, intent),
            presentation=self.build_presentation(overlays),
        )

    def choose_basemap(self, plan: ExecutionPlan) -> str:
        if plan.basemap_id:
            return plan.basemap_id
        if plan.intent_id in {"weather", "air_quality"}:
            return "osm_dark"
        if plan.intent_id in {"imagery", "satellite"}:
            return "gibs_satellite"
        if plan.intent_id in {"solar", "terrain"}:
            return "osm_terrain"
        return "osm_default"

    def build_viewport(
        self,
        location: ResolvedLocation,
        intent: NormalizedIntent,
    ) -> ViewportPolicy:
        radius_m = 2500.0
        intent_text = " ".join(
            [
                intent.intent_id,
                intent.intent_label,
                *intent.task_tags,
                *intent.intent_tags,
            ]
        ).lower()
        if any(marker in intent_text for marker in ("exact_address", "exact address", "address")):
            radius_m = 1000.0
        elif any(marker in intent_text for marker in ("wide", "city", "city_level", "entire city")):
            radius_m = 25000.0
        elif any(marker in intent_text for marker in ("region", "regional", "country", "island", "province")):
            radius_m = 100000.0
        elif intent.intent_id in {"traffic", "air_quality"}:
            radius_m = 4500.0
        return ViewportPolicy(
            center_latitude=location.latitude,
            center_longitude=location.longitude,
            radius_m=radius_m,
        )

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
