from __future__ import annotations

from urllib.parse import urlencode

from server.services.geospatial.providers.base import (
    GeospatialProvider,
    ProviderRequest,
    ProviderResponse,
)


class USGSProvider(GeospatialProvider):
    provider_id = "usgs"

    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        if request.capability_id == "usgs_water_gauges":
            return self._water_services(request)
        return self._earthquakes(request)

    def _earthquakes(self, request: ProviderRequest) -> ProviderResponse:
        feed = str(request.params.get("feed") or "all_day").strip()
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={
                "renderingMode": "clustered-points",
                "featuresUrl": f"https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/{feed}.geojson",
                "timeMode": "current",
            },
            attribution=["U.S. Geological Survey"],
        )

    def _water_services(self, request: ProviderRequest) -> ProviderResponse:
        params = {
            "format": "json",
            "siteStatus": "active",
            "parameterCd": request.params.get("parameterCd") or "00065",
        }
        if request.bbox is not None:
            west, south, east, north = request.bbox
            params["bBox"] = f"{west},{south},{east},{north}"
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={
                "renderingMode": "clustered-points",
                "featuresUrl": f"https://waterservices.usgs.gov/nwis/iv/?{urlencode(params)}",
                "format": "json",
            },
            attribution=["U.S. Geological Survey"],
        )
