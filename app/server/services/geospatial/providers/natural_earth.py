from __future__ import annotations

from server.services.geospatial.providers.base import ProviderRequest, ProviderResponse


class NaturalEarthProvider:
    provider_id = "natural_earth"

    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={
                "type": "dataset-ingestion",
                "status": "source-ready",
                "downloadUrl": "https://www.naturalearthdata.com/downloads/",
                "message": "Natural Earth data is exposed through the configured dataset ingestion pipeline.",
            },
            attribution=["Natural Earth"],
        )
