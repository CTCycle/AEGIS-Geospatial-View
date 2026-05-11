from __future__ import annotations

import os
from urllib.parse import urlencode

from server.services.geospatial.providers._request import request_center, request_radius_m
from server.services.geospatial.providers.base import (
    GeospatialProvider,
    ProviderRequest,
    ProviderResponse,
)


class OpenChargeMapProvider(GeospatialProvider):
    provider_id = "openchargemap"

    def __init__(self, *, api_key: str | None = None) -> None:
        self.api_key = api_key

    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        latitude, longitude = request_center(request)
        radius_m = request_radius_m(request, 10000.0)
        params = {
            "output": "json",
            "latitude": f"{latitude:.6f}",
            "longitude": f"{longitude:.6f}",
            "distance": f"{radius_m / 1000:.1f}",
            "distanceunit": "KM",
            "maxresults": str(int(request.params.get("maxresults") or 100)),
        }
        api_key = (self.api_key or os.getenv("OPENCHARGEMAP_API_KEY") or "").strip()
        if api_key:
            params["key"] = api_key
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={
                "renderingMode": "clustered-points",
                "featuresUrl": f"https://api.openchargemap.io/v3/poi/?{urlencode(params)}",
            },
            attribution=["Open Charge Map"],
        )
