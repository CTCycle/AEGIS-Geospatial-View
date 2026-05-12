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
                "status": "requires-ingestion",
                "message": "Natural Earth data is exposed through the dataset ingestion pipeline.",
            },
            attribution=["Natural Earth"],
            warnings=["Run the configured ingestion manifest before map rendering."],
        )
