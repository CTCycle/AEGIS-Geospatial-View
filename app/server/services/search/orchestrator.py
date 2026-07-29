from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any

from server.domain.geographics import LocationSearchRequest, MapSession
from server.services.geospatial.capability_registry import CapabilityRegistry
from server.services.geospatial.render_descriptors import RenderDescriptorService
from server.services.geospatial.rainviewer import RainViewerService

###############################################################################
class LocationSearchOrchestrator:

    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        capability_registry: CapabilityRegistry | None = None,
        rainviewer_service: RainViewerService | None = None,
        render_descriptor_service: RenderDescriptorService | None = None,
    ) -> None:
        self.capability_registry = capability_registry or CapabilityRegistry()
        self.rainviewer_service = rainviewer_service or RainViewerService()
        self.render_descriptor_service = render_descriptor_service or RenderDescriptorService(
            capability_registry=self.capability_registry,
            rainviewer_service=self.rainviewer_service,
        )

    # -------------------------------------------------------------------------
    async def execute(self, payload: LocationSearchRequest) -> MapSession:
        self.capability_registry.load_capabilities()
        basemap = await self.render_descriptor_service.build_basemap_descriptor(
            payload.basemap_id
        )
        overlays: list[dict[str, object]] = []
        failed_overlays: list[dict[str, str]] = []
        warnings: list[str] = []
        effective_basemap_id = (
            str(basemap.get("id"))
            if isinstance(basemap, dict) and basemap.get("id")
            else payload.basemap_id
        )
        for overlay_id in payload.overlay_ids:
            overlay_result = await self.render_descriptor_service.build_overlay_descriptor(
                overlay_id,
                request=payload,
            )
            if overlay_result is None:
                reason = "not available in the capability catalog"
                failed_overlays.append({"id": overlay_id, "reason": reason})
                warnings.append(
                    f"Overlay '{overlay_id}' is {reason}."
                )
                continue
            descriptor, overlay_warnings = overlay_result
            overlays.append(descriptor)
            warnings.extend(overlay_warnings)
        for selection in payload.provider_layer_selections:
            selection_id = f"{selection.provider_id}:{selection.layer_id}"
            try:
                descriptor, overlay_warnings = await self.render_descriptor_service.build_provider_layer_overlay(
                    provider_id=selection.provider_id,
                    layer_id=selection.layer_id,
                    request=payload,
                )
            except Exception as exc:  # noqa: BLE001
                reason = str(exc) or "provider layer could not be rendered"
                failed_overlays.append({"id": selection_id, "reason": reason})
                warnings.append(f"Provider layer '{selection_id}' failed: {reason}.")
                continue
            if selection.time and isinstance(descriptor.get("render"), dict):
                descriptor["time"] = selection.time
                descriptor["render"]["time"] = selection.time
            if selection.style and isinstance(descriptor.get("render"), dict):
                descriptor["style"] = selection.style
                descriptor["render"]["style"] = selection.style
            if selection.format and isinstance(descriptor.get("render"), dict):
                descriptor["format"] = selection.format
                descriptor["render"]["format"] = selection.format
            overlays.append(descriptor)
            warnings.extend(overlay_warnings)
        rendered_overlay_ids = [
            str(overlay["id"])
            for overlay in overlays
            if isinstance(overlay.get("id"), str)
        ]
        return MapSession(
            session_id=f"map-{int(datetime.now(UTC).timestamp())}",
            resolved_location=payload.resolved_location,
            basemap_id=effective_basemap_id,
            overlay_ids=rendered_overlay_ids,
            viewport=payload.viewport,
            center={
                "latitude": payload.viewport.center_latitude,
                "longitude": payload.viewport.center_longitude,
            },
            bounds=payload.viewport.bbox or self._bounds_from_viewport(payload.viewport),
            basemap=basemap,
            overlays=overlays,
            requested_overlay_ids=[
                *list(payload.overlay_ids),
                *[
                    f"{selection.provider_id}:{selection.layer_id}"
                    for selection in payload.provider_layer_selections
                ],
            ],
            rendered_overlay_ids=rendered_overlay_ids,
            failed_overlays=failed_overlays,
            compliance_warnings=warnings,
            payload={
                "action_id": payload.action_id,
                "time_mode": payload.time_mode,
                "presentation": payload.presentation.model_dump(mode="json"),
            },
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def _bounds_from_viewport(viewport: Any) -> list[float] | None:
        latitude = getattr(viewport, "center_latitude", None)
        longitude = getattr(viewport, "center_longitude", None)
        radius_m = getattr(viewport, "radius_m", None)
        if not isinstance(latitude, int | float) or not isinstance(
            longitude, int | float
        ):
            return None
        if not isinstance(radius_m, int | float) or radius_m <= 0:
            return None
        lat_delta = radius_m / 111_320.0
        lon_delta = radius_m / (
            111_320.0 * max(abs(math.cos(math.radians(float(latitude)))), 0.01)
        )
        return [
            max(-180.0, float(longitude) - lon_delta),
            max(-90.0, float(latitude) - lat_delta),
            min(180.0, float(longitude) + lon_delta),
            min(90.0, float(latitude) + lat_delta),
        ]
