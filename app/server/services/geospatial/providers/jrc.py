"""JRC Global Surface Water (1984-2024) map tiles, served through the AEGIS tile proxy.

The tiles are RGB renderings of the Pekel et al. (2016) water products. They
show where and how often water occurred but carry no numeric values, so the
capabilities are render-only.
"""

from __future__ import annotations

from server.services.geospatial.providers.base import (
    ProviderInvalidQueryError,
    ProviderRequest,
    ProviderResponse,
)

JRC_TILE_ROOT = "https://storage.googleapis.com/water-world/tiles2024"
JRC_ATTRIBUTION = "Source: EC JRC/Google (Pekel et al., Nature 2016)"
JRC_MAX_ZOOM = 13
JRC_LAYERS: dict[str, tuple[str, str]] = {
    "jrc_surface_water_occurrence": ("occurrence", "Share of 1984-2024 observations with water"),
    "jrc_surface_water_change": ("change", "Change in water occurrence intensity, 1984-1999 vs 2000-2024"),
}


###############################################################################
class JRCSurfaceWaterProvider:
    provider_id = "jrc"

    # -------------------------------------------------------------------------
    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        layer = JRC_LAYERS.get(request.capability_id)
        if layer is None:
            raise ProviderInvalidQueryError(f"Unknown JRC surface water layer '{request.capability_id}'.")
        name, label = layer
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={
                "renderingMode": "raster-tile",
                "tileUrl": f"{JRC_TILE_ROOT}/{name}/{{z}}/{{x}}/{{y}}.png",
                "maxZoom": JRC_MAX_ZOOM,
                "legend": {"type": "surface-water", "label": label},
                "freshnessLabel": "JRC Global Surface Water 1984-2024 release",
            },
            attribution=[JRC_ATTRIBUTION],
            result_type="raster",
            coverage={"type": "global", "temporal_coverage": "1984-2024", "numeric_values": False},
        )
