from __future__ import annotations

from server.services.geospatial.providers.base import (
    GeospatialProvider,
    ProviderAuthError,
    ProviderRequest,
    ProviderResponse,
)


class TomTomProvider(GeospatialProvider):
    provider_id = "tomtom"

    def __init__(self, *, api_key: str | None = None) -> None:
        self.api_key = (api_key or "").strip()

    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        if not self.api_key:
            raise ProviderAuthError("TomTom API key is required.")
        layer = "relative0"
        style = "absolute"
        tile_url = (
            "https://api.tomtom.com/traffic/map/4/tile/flow/"
            f"{style}/{layer}/{{z}}/{{x}}/{{y}}.png?key={self.api_key}"
        )
        if "basic" in request.capability_id:
            tile_url = (
                "https://api.tomtom.com/map/1/tile/basic/main/"
                f"{{z}}/{{x}}/{{y}}.png?key={self.api_key}"
            )
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={
                "renderingMode": "raster-tile",
                "tileUrl": tile_url,
                "credentialPolicy": "server-side-or-existing-browser-key-only",
            },
            attribution=["TomTom"],
        )
