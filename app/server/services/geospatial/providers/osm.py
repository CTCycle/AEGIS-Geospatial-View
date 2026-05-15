from __future__ import annotations

from server.services.geospatial.providers.base import ProviderRequest, ProviderResponse


class OSMProvider:
    provider_id = "osm"

    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={
                "type": "metadata-only",
                "status": "use-overpass-or-tile-proxy",
                "message": "OSM runtime access is handled by Overpass for features and the tile proxy for basemaps.",
            },
            attribution=["OpenStreetMap contributors"],
        )
