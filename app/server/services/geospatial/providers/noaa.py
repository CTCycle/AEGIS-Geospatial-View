from __future__ import annotations

from urllib.parse import urlencode

from server.services.geospatial.providers.base import (
    GeospatialProvider,
    ProviderRequest,
    ProviderResponse,
)


class NOAAProvider(GeospatialProvider):
    provider_id = "noaa"

    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        if request.capability_id == "noaa_coops_water_levels":
            return self._coops_water_levels(request)
        if request.capability_id == "noaa_radar":
            return self._radar_tiles(request)
        return self._weather_alerts(request)

    def _weather_alerts(self, request: ProviderRequest) -> ProviderResponse:
        params: dict[str, str] = {"status": "actual", "message_type": "alert"}
        if request.bbox is not None:
            west, south, east, north = request.bbox
            params["point"] = f"{(south + north) / 2},{(west + east) / 2}"
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={
                "renderingMode": "geojson",
                "featuresUrl": f"https://api.weather.gov/alerts/active?{urlencode(params)}",
                "format": "geojson",
            },
            attribution=["NOAA National Weather Service"],
        )

    def _radar_tiles(self, request: ProviderRequest) -> ProviderResponse:
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={
                "renderingMode": "raster-tile",
                "tileUrl": "https://opengeo.ncep.noaa.gov/geoserver/conus/conus_bref_qcd/ows?service=WMS&version=1.3.0&request=GetMap&layers=conus_bref_qcd&styles=&format=image/png&transparent=true&width=256&height=256&crs=EPSG:3857&bbox={bbox-epsg-3857}",
                "format": "wms",
            },
            attribution=["NOAA/NCEP nowCOAST"],
        )

    def _coops_water_levels(self, request: ProviderRequest) -> ProviderResponse:
        params = {
            "product": "water_level",
            "datum": "MLLW",
            "time_zone": "gmt",
            "units": "metric",
            "format": "json",
        }
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={
                "renderingMode": "clustered-points",
                "featuresUrl": f"https://api.tidesandcurrents.noaa.gov/api/prod/datagetter?{urlencode(params)}",
                "format": "json",
            },
            attribution=["NOAA CO-OPS"],
        )
