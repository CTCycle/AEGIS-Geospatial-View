from __future__ import annotations

from server.services.geospatial.providers.base import (
    GeospatialProvider,
    ProviderRequest,
    ProviderResponse,
)

FEMA_NFHL_EXPORT_URL = (
    "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/export?"
    "bbox={bbox-epsg-3857}&bboxSR=3857&imageSR=3857&size=256,256&format=png32"
    "&transparent=true&f=image"
)

###############################################################################
class FEMAProvider(GeospatialProvider):
    provider_id = "fema"

    # -------------------------------------------------------------------------
    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={
                "renderingMode": "raster-tile",
                "tileUrl": FEMA_NFHL_EXPORT_URL,
                "layer": "NFHL",
                "legend": {"type": "flood-zone", "label": "NFHL flood hazard zone"},
                "freshnessLabel": "FEMA NFHL public map service",
            },
            result_type="raster",
            attribution=["Federal Emergency Management Agency"],
        )
