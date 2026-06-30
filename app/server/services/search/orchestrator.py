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
        warnings: list[str] = []
        if (
            isinstance(basemap, dict)
            and basemap.get("tile_url") is None
            and basemap.get("provider") in {"tomtom", "geoapify"}
        ):
            warnings.append(
                f"{payload.basemap_id}: provider API key is required; "
                "falling back to osm_default."
            )
            basemap = await self.render_descriptor_service.build_basemap_descriptor(
                "osm_default"
            )
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
                warnings.append(
                    f"Overlay '{overlay_id}' is not available in the capability catalog."
                )
                continue
            descriptor, overlay_warnings = overlay_result
            overlays.append(descriptor)
            warnings.extend(overlay_warnings)
        return MapSession(
            session_id=f"map-{int(datetime.now(UTC).timestamp())}",
            resolved_location=payload.resolved_location,
            basemap_id=effective_basemap_id,
            overlay_ids=list(payload.overlay_ids),
            viewport=payload.viewport,
            center={
                "latitude": payload.viewport.center_latitude,
                "longitude": payload.viewport.center_longitude,
            },
            bounds=payload.viewport.bbox or self._bounds_from_viewport(payload.viewport),
            basemap=basemap,
            overlays=overlays,
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
