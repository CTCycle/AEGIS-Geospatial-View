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


class NRELProvider(GeospatialProvider):
    provider_id = "nrel"

    def __init__(self, *, api_key: str | None = None) -> None:
        self.api_key = api_key

    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        api_key = (self.api_key or os.getenv("NREL_API_KEY") or "").strip()
        if not api_key:
            raise ProviderAuthError("NREL_API_KEY is required for AFDC alternative fuel station access.")
        latitude, longitude = request_center(request)
        radius_m = request_radius_m(request, 10000.0)
        params = {
            "api_key": api_key,
            "latitude": f"{latitude:.6f}",
            "longitude": f"{longitude:.6f}",
            "radius": f"{radius_m / 1609.344:.1f}",
            "format": "json",
        }
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={
                "renderingMode": "clustered-points",
                "featuresUrl": f"https://developer.nrel.gov/api/alt-fuel-stations/v1/nearest.json?{urlencode(params)}",
            },
            attribution=["National Renewable Energy Laboratory"],
        )
