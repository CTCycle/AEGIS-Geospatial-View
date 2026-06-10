from __future__ import annotations

from server.services.geospatial.providers.base import ProviderRequest, ProviderResponse


###############################################################################
class OvertureProvider:
    provider_id = "overture"

    # -------------------------------------------------------------------------
    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={
                "type": "dataset-ingestion",
                "status": "source-ready",
                "downloadUrl": "https://docs.overturemaps.org/getting-data/",
                "message": "Overture Maps capabilities are available through preprocessing from the public cloud dataset.",
            },
            attribution=["Overture Maps Foundation"],
        )
