from __future__ import annotations

from server.services.geospatial.providers.base import (
    GeospatialProvider,
    ProviderAuthError,
    ProviderRequest,
    ProviderResponse,
)


class GeoapifyProvider(GeospatialProvider):
    provider_id = "geoapify"

    def __init__(self, *, api_key: str | None = None) -> None:
        self.api_key = (api_key or "").strip()

    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        if not self.api_key:
            raise ProviderAuthError("Geoapify API key is required.")
        if "osm" in request.capability_id:
            return ProviderResponse(
                capability_id=request.capability_id,
                provider_id=self.provider_id,
                payload={
                    "renderingMode": "raster-tile",
                    "tileUrl": (
                        "https://maps.geoapify.com/v1/tile/osm-bright/"
                        f"{{z}}/{{x}}/{{y}}.png?apiKey={self.api_key}"
                    ),
                    "credentialPolicy": "server-side-or-existing-browser-key-only",
                },
                attribution=["Geoapify, OpenStreetMap contributors"],
            )
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={
                "renderingMode": "clustered-points",
                "featuresEndpoint": "/api/geospatial/layers/geoapify_amenities/features",
                "credentialPolicy": "server-side-only",
            },
            attribution=["Geoapify, OpenStreetMap contributors"],
        )
