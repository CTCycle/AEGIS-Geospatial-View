from __future__ import annotations

from server.services.geospatial.providers.base import ProviderRequest, ProviderResponse


class LocalOpenDataProvider:
    provider_id = "local_open_data"

    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={
                "type": "dataset-ingestion",
                "status": "requires-local-source",
                "message": "Local open-data layers require a configured download or file source manifest.",
            },
            attribution=["Local open data provider"],
            warnings=["No live provider is queried for local open-data templates."],
        )
