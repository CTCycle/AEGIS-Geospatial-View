from __future__ import annotations

from server.services.geospatial.providers.base import ProviderAuthError, ProviderRequest, ProviderResponse


class TransitlandProvider:
    provider_id = "transitland"

    def __init__(self, *, api_key: str | None = None) -> None:
        self.api_key = api_key

    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        if not self.api_key:
            raise ProviderAuthError("Transitland access requires a configured API key.")
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={"type": "search-index", "status": "not-queried", "features": []},
            attribution=["Transitland"],
            warnings=["Transitland feed discovery is registered but requires a bounded query implementation for live use."],
        )
