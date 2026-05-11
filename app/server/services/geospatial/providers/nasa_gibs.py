from __future__ import annotations

from server.common.constants import GIBS_WMS_BASE_ENDPOINTS, NASA_ATTRIBUTION
from server.services.geospatial.providers.base import (
    GeospatialProvider,
    ProviderRequest,
    ProviderResponse,
)


class NASAGIBSProvider(GeospatialProvider):
    provider_id = "gibs"

    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        crs = str(request.params.get("crs") or "EPSG:3857")
        endpoint = GIBS_WMS_BASE_ENDPOINTS.get(crs, GIBS_WMS_BASE_ENDPOINTS["EPSG:3857"])
        layer = str(request.params.get("layer") or request.capability_id)
        time_value = request.params.get("time")
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={
                "renderingMode": "wms",
                "serviceUrl": endpoint,
                "layers": [layer],
                "crs": crs,
                "time": time_value,
                "format": str(request.params.get("format") or "image/png"),
            },
            attribution=[NASA_ATTRIBUTION],
        )
