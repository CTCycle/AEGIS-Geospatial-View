from __future__ import annotations

import os
from urllib.parse import urlencode

from server.services.geospatial.providers._request import request_center, request_radius_m
from server.services.geospatial.providers.base import (
    GeospatialProvider,
    ProviderAuthError,
    ProviderRequest,
    ProviderResponse,
)


class OpenTripMapProvider(GeospatialProvider):
    provider_id = "opentripmap"

    def __init__(self, *, api_key: str | None = None) -> None:
        self.api_key = api_key

    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        api_key = (self.api_key or os.getenv("OPENTRIPMAP_API_KEY") or "").strip()
        if not api_key:
            raise ProviderAuthError("OPENTRIPMAP_API_KEY is required for OpenTripMap tourism POIs.")
        latitude, longitude = request_center(request)
        radius_m = request_radius_m(request, 2500.0)
        params = {
            "apikey": api_key,
            "lat": f"{latitude:.6f}",
            "lon": f"{longitude:.6f}",
            "radius": str(int(radius_m)),
            "format": "geojson",
            "limit": str(int(request.params.get("limit") or 100)),
            "kinds": str(request.params.get("kinds") or "interesting_places"),
        }
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={
                "renderingMode": "clustered-points",
                "featuresUrl": f"https://api.opentripmap.com/0.1/en/places/radius?{urlencode(params)}",
            },
            attribution=["OpenTripMap"],
        )
