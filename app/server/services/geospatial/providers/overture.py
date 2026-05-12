from __future__ import annotations

from server.services.geospatial.providers.base import ProviderRequest, ProviderResponse


class OvertureProvider:
    provider_id = "overture"

    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={
                "type": "dataset-ingestion",
                "status": "requires-ingestion",
                "message": "Overture Maps capabilities require preprocessing from the public cloud dataset.",
            },
            attribution=["Overture Maps Foundation"],
            warnings=["Overture is not queried live by the runtime provider path."],
        )
