from __future__ import annotations

from server.services.geospatial.providers.base import ProviderAuthError, ProviderRequest, ProviderResponse


class MapillaryProvider:
    provider_id = "mapillary"

    def __init__(self, *, access_token: str | None = None) -> None:
        self.access_token = access_token

    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        if not self.access_token:
            raise ProviderAuthError("Mapillary access requires a configured token.")
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={"type": "metadata-only", "status": "not-enabled"},
            attribution=["Mapillary"],
            warnings=["Mapillary is registered as an optional camera/street-level imagery provider."],
        )
