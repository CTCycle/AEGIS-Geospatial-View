from __future__ import annotations

from server.services.geospatial.providers.base import ProviderRequest, ProviderResponse


###############################################################################
class OpenAddressesProvider:
    provider_id = "openaddresses"

    # -------------------------------------------------------------------------
    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={
                "type": "dataset-ingestion",
                "status": "source-ready",
                "downloadUrl": "https://batch.openaddresses.io/data",
                "message": "OpenAddresses points are available through configured dataset ingestion and indexing.",
            },
            attribution=["OpenAddresses"],
        )
