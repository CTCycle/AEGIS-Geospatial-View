from __future__ import annotations

from urllib.parse import urlencode

from server.services.geospatial.providers.base import (
    GeospatialProvider,
    ProviderRequest,
    ProviderResponse,
    ProviderUnavailableError,
)

###############################################################################
class ArcGISRestProvider(GeospatialProvider):
    provider_id = "arcgis"

    # -------------------------------------------------------------------------
    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        service_url = str(request.params.get("service_url") or "").strip()
        if not service_url:
            raise ProviderUnavailableError("ArcGIS REST service_url is required.")
        params = {
            "f": "geojson",
            "outFields": str(request.params.get("out_fields") or "*"),
            "where": str(request.params.get("where") or "1=1"),
        }
        if request.bbox is not None:
            min_lon, min_lat, max_lon, max_lat = request.bbox
            params.update(
                {
                    "geometry": f"{min_lon},{min_lat},{max_lon},{max_lat}",
                    "geometryType": "esriGeometryEnvelope",
                    "inSR": "4326",
                    "spatialRel": "esriSpatialRelIntersects",
                    "outSR": "4326",
                }
            )
        separator = "&" if "?" in service_url else "?"
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={
                "renderingMode": "geojson",
                "featuresUrl": f"{service_url}{separator}{urlencode(params)}",
            },
            attribution=[str(request.params.get("attribution") or "ArcGIS REST")],
        )
