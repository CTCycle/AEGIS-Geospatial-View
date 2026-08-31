from __future__ import annotations

from server.common.typing import is_json_array, is_json_object, json_array, json_object

import math
from typing import Any

from server.common.logger import logger as LOGGER
from server.domain.agent.decision import ExecutionPlan, ResolvedLocation
from server.contracts.extraction import (
    NormalizedAction,
    TurnParseResult,
    ViewportIntent,
)
from server.contracts.geospatial import (
    LocationSearchRequest,
    PresentationPolicy,
    ProviderLayerSelection,
    ViewportPolicy,
)
from server.services.geospatial.capability_registry import CapabilityRegistry


###############################################################################
class RequestBuilder:
    DEFAULT_RADIUS_M = 2500.0
    MIN_RADIUS_M = 120.0
    MAX_RADIUS_M = 250000.0
    SCOPE_RADII_M = {
        "building": 180.0,
        "street": 350.0,
        "neighborhood": 1200.0,
        "district": 4000.0,
        "city": 18000.0,
        "region": 90000.0,
        "country": 250000.0,
        "auto": DEFAULT_RADIUS_M,
    }

    # -------------------------------------------------------------------------
    def __init__(self, capability_registry: CapabilityRegistry | None = None) -> None:
        self.capability_registry = capability_registry

    # -------------------------------------------------------------------------
    def build_location_search_request(
        self,
        plan: ExecutionPlan,
        location: ResolvedLocation,
        *,
        turn_contract: TurnParseResult | None = None,
        active_visualization: dict[str, Any] | None = None,
        provider_layer_selections: list[ProviderLayerSelection] | None = None,
    ) -> LocationSearchRequest:
        action = (
            turn_contract.normalized_action
            if turn_contract is not None
            else NormalizedAction(
                action_id=plan.action_id,
                action_label=plan.action_id,
                task_tags=[],
                action_tags=[],
            )
        )
        viewport_intent = (
            turn_contract.viewport_intent if turn_contract is not None else None
        )
        overlays = list(plan.overlay_ids)
        request = LocationSearchRequest(
            resolved_location=location,
            action_id=plan.action_id,
            time_mode="current",
            basemap_id=self.choose_basemap(plan),
            overlay_ids=overlays,
            provider_layer_selections=list(provider_layer_selections or []),
            viewport=self.build_viewport(
                location,
                action,
                viewport_intent=viewport_intent,
                active_visualization=active_visualization,
            ),
            presentation=self.build_presentation(overlays),
            viewport_intent=viewport_intent,
            poi_categories=list(turn_contract.poi_categories)
            if turn_contract is not None
            else [],
        )
        LOGGER.info(
            "map_request_built action=%s basemap=%s overlays=%d viewport_scope=%s tighten=%s radius_m=%.1f bbox=%s location_type=%s",
            request.action_id,
            request.basemap_id,
            len(request.overlay_ids),
            viewport_intent.scope if viewport_intent is not None else None,
            viewport_intent.tighten_relative_to_active
            if viewport_intent is not None
            else None,
            request.viewport.radius_m,
            request.viewport.bbox,
            location.location_type,
        )
        return request

    # -------------------------------------------------------------------------
    def choose_basemap(self, plan: ExecutionPlan) -> str:
        if plan.basemap_id:
            return plan.basemap_id
        if self.capability_registry is not None:
            candidates: list[tuple[bool, str]] = []
            for basemap in self.capability_registry.list_basemaps():
                capability_id = str(basemap.get("id") or "").strip()
                if not capability_id:
                    continue
                agentic_use = json_object(basemap.get("agenticUse"))
                default_enabled = bool(agentic_use.get("defaultEnabled"))
                candidates.append((not default_enabled, capability_id))
            if candidates:
                return min(candidates)[1]
        # The standalone builder remains usable in isolated unit tests. The
        # application composition supplies the catalog-backed default above.
        return "osm_default"

    # -------------------------------------------------------------------------
    def build_viewport(
        self,
        location: ResolvedLocation,
        action: NormalizedAction,
        *,
        viewport_intent: ViewportIntent | None = None,
        active_visualization: dict[str, Any] | None = None,
    ) -> ViewportPolicy:
        _ = action
        current_viewport = self._coerce_active_viewport(active_visualization)
        location_changed = self._active_location_differs(location, active_visualization)
        if (
            viewport_intent is not None
            and viewport_intent.scope == "preserve_current"
            and current_viewport is not None
            and not location_changed
        ):
            return current_viewport

        explicit_scope = (
            viewport_intent.scope
            if viewport_intent is not None
            and viewport_intent.scope != "preserve_current"
            else None
        )
        if (
            viewport_intent is not None
            and viewport_intent.tighten_relative_to_active
            and current_viewport is not None
            and not location_changed
        ):
            tightened = self._tighten_viewport(
                current_viewport,
                viewport_intent.radius_hint_m,
                explicit_scope or "street",
            )
            if tightened is not None:
                return tightened

        scope = explicit_scope or self._scope_from_resolved_location(location) or "auto"
        radius_m = (
            viewport_intent.radius_hint_m
            if viewport_intent and viewport_intent.radius_hint_m
            else self.SCOPE_RADII_M.get(scope, self.DEFAULT_RADIUS_M)
        )
        radius_m = self._clamp_radius(radius_m)
        bbox = self._padded_bbox_for_scope(location.bbox, scope)
        if bbox is not None:
            return ViewportPolicy(
                center_latitude=location.latitude,
                center_longitude=location.longitude,
                radius_m=max(radius_m, self._radius_from_bbox(bbox)),
                bbox=bbox,
            )
        return ViewportPolicy(
            center_latitude=location.latitude,
            center_longitude=location.longitude,
            radius_m=radius_m,
        )

    # -------------------------------------------------------------------------
    def build_presentation(self, overlays: list[str]) -> PresentationPolicy:
        high_contrast = False
        if self.capability_registry is not None:
            for overlay_id in overlays:
                capability = self.capability_registry.get_capability(overlay_id)
                metadata = (
                    json_object(capability.get("metadata")) if capability else {}
                )
                map_type_tags = json_array(metadata.get("map_type_tags"))
                if map_type_tags and any(
                    str(tag).casefold() in {"thematic", "operational"}
                    for tag in map_type_tags
                ):
                    high_contrast = True
                    break
        return PresentationPolicy(
            emphasize_overlays=bool(overlays),
            high_contrast=high_contrast,
            show_legend=bool(overlays),
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def _scope_from_resolved_location(location: ResolvedLocation) -> str | None:
        location_type = str(location.location_type or "").lower()
        location_class = str(location.location_class or "").lower()
        if location_type in {
            "house",
            "building",
            "residential",
            "commercial",
            "address",
            "street",
            "road",
            "pedestrian",
        }:
            return "street"
        if location_class == "highway":
            return "street"
        if location_type in {"neighbourhood", "suburb", "quarter"}:
            return "neighborhood"
        if location_type in {"city", "town", "village", "municipality"}:
            return "city"
        if location_type in {"state", "region", "county", "province"}:
            return "region"
        if location_type in {"country"}:
            return "country"
        return None

    # -------------------------------------------------------------------------
    def _tighten_viewport(
        self,
        viewport: ViewportPolicy,
        radius_hint_m: float | None,
        scope: str,
    ) -> ViewportPolicy | None:
        target_radius = (
            radius_hint_m
            if radius_hint_m is not None
            else self.SCOPE_RADII_M.get(scope, self.SCOPE_RADII_M["street"])
        )
        radius_m = min(
            self._clamp_radius(target_radius),
            self._clamp_radius(viewport.radius_m * 0.35),
        )
        if radius_m >= viewport.radius_m:
            radius_m = self._clamp_radius(viewport.radius_m * 0.5)
        if radius_m >= viewport.radius_m:
            return None
        return ViewportPolicy(
            center_latitude=viewport.center_latitude,
            center_longitude=viewport.center_longitude,
            radius_m=radius_m,
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def _coerce_active_viewport(
        active_visualization: dict[str, Any] | None,
    ) -> ViewportPolicy | None:
        if not is_json_object(active_visualization):
            return None
        viewport = active_visualization.get("viewport")
        if not is_json_object(viewport):
            return None
        try:
            return ViewportPolicy.model_validate(viewport)
        except Exception:
            return None

    # -------------------------------------------------------------------------
    @staticmethod
    def _active_location_differs(
        location: ResolvedLocation,
        active_visualization: dict[str, Any] | None,
    ) -> bool:
        if not is_json_object(active_visualization):
            return False
        active_location = active_visualization.get("resolved_location")
        if not is_json_object(active_location):
            return False
        try:
            active_latitude = float(active_location["latitude"])
            active_longitude = float(active_location["longitude"])
            return (
                abs(active_latitude - float(location.latitude)) > 1e-6
                or abs(active_longitude - float(location.longitude)) > 1e-6
            )
        except KeyError, TypeError, ValueError:
            return False

    # -------------------------------------------------------------------------
    def _padded_bbox_for_scope(
        self,
        bbox: list[float] | None,
        scope: str,
    ) -> list[float] | None:
        if not self._is_bbox(bbox):
            return None
        if scope not in {"building", "street", "neighborhood", "district"}:
            return None
        assert bbox is not None
        min_lon, min_lat, max_lon, max_lat = [float(str(item)) for item in bbox]
        lon_pad_factor = 0.2 if scope in {"building", "street"} else 0.35
        lat_pad_factor = lon_pad_factor
        lon_span = max(
            max_lon - min_lon, 0.0004 if scope in {"building", "street"} else 0.002
        )
        lat_span = max(
            max_lat - min_lat, 0.0003 if scope in {"building", "street"} else 0.0015
        )
        lon_pad = lon_span * lon_pad_factor
        lat_pad = lat_span * lat_pad_factor
        return [
            max(-180.0, min_lon - lon_pad),
            max(-90.0, min_lat - lat_pad),
            min(180.0, max_lon + lon_pad),
            min(90.0, max_lat + lat_pad),
        ]

    # -------------------------------------------------------------------------
    def _radius_from_bbox(self, bbox: list[float]) -> float:
        min_lon, min_lat, max_lon, max_lat = [float(item) for item in bbox]
        center_lat = (min_lat + max_lat) / 2.0
        lat_radius = ((max_lat - min_lat) / 2.0) * 111_320.0
        lon_radius = (
            ((max_lon - min_lon) / 2.0)
            * 111_320.0
            * max(abs(math.cos(math.radians(center_lat))), 0.01)
        )
        return self._clamp_radius(max(lat_radius, lon_radius))

    # -------------------------------------------------------------------------
    def _clamp_radius(self, radius_m: float) -> float:
        return max(self.MIN_RADIUS_M, min(float(radius_m), self.MAX_RADIUS_M))

    # -------------------------------------------------------------------------
    @staticmethod
    def _is_bbox(value: list[float] | None) -> bool:
        return (
            is_json_array(value)
            and len(value) == 4
            and all(isinstance(item, int | float) for item in value)
        )
