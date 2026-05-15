from __future__ import annotations

from server.services.geospatial.providers.base import ProviderRequest, ProviderResponse


class FallbackTileProvider:
    provider_id = "fallback"

    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={
                "type": "raster-tile",
                "status": "client-rendered",
                "message": "Fallback basemap tiles are rendered from normalized manifest URLs.",
            },
            attribution=["OpenStreetMap contributors"],
        )
