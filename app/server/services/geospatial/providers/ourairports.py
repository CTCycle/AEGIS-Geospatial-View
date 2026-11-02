from __future__ import annotations

from server.services.geospatial.providers.base import (
    GeospatialProvider,
    ProviderRequest,
    ProviderResponse,
    ProviderUnavailableError,
)

###############################################################################
class OurAirportsProvider(GeospatialProvider):
    provider_id = "ourairports"

    # -------------------------------------------------------------------------
    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        if request.params.get("live"):
            # The source is a CSV for the ingestion pipeline; at query time it
            # has no airport records, and a descriptor is not evidence.
            raise ProviderUnavailableError(
                "OurAirports provides no live airport records; its CSV is only "
                "available through dataset ingestion."
            )
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={
                "type": "dataset-ingestion",
                "renderingMode": "clustered-points",
                "downloadUrl": "https://davidmegginson.github.io/ourairports-data/airports.csv",
                "status": "source-ready",
                "message": "OurAirports CSV data is normalized by the dataset ingestion pipeline.",
            },
            attribution=["OurAirports"],
        )
