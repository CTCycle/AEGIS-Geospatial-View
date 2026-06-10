from __future__ import annotations

from server.services.geospatial.providers.base import (
    GeospatialProvider,
    ProviderRequest,
    ProviderResponse,
)


###############################################################################
class OurAirportsProvider(GeospatialProvider):
    provider_id = "ourairports"

    # -------------------------------------------------------------------------
    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={
                "renderingMode": "clustered-points",
                "downloadUrl": "https://davidmegginson.github.io/ourairports-data/airports.csv",
                "status": "source-ready",
                "message": "OurAirports CSV data is normalized by the dataset ingestion pipeline.",
            },
            attribution=["OurAirports"],
        )
