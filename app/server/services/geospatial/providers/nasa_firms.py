from __future__ import annotations

import os
from urllib.parse import urlencode

from server.services.geospatial.providers.base import (
    GeospatialProvider,
    ProviderAuthError,
    ProviderRequest,
    ProviderResponse,
)


class NASAFIRMSProvider(GeospatialProvider):
    provider_id = "nasa_firms"

    def __init__(self, *, api_key: str | None = None) -> None:
        self.api_key = api_key

    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        api_key = (self.api_key or os.getenv("NASA_API_KEY") or "").strip()
        if not api_key:
            raise ProviderAuthError("NASA_API_KEY is required for NASA FIRMS active fire access.")
        west, south, east, north = request.bbox or (-180.0, -90.0, 180.0, 90.0)
        params = urlencode({"bbox": f"{west},{south},{east},{north}", "key": api_key})
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={
                "renderingMode": "clustered-points",
                "featuresUrl": f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{api_key}/VIIRS_SNPP_NRT/{west},{south},{east},{north}/1",
                "query": params,
            },
            attribution=["NASA FIRMS"],
        )
