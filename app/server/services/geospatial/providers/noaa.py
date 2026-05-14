from __future__ import annotations

from urllib.parse import urlencode

from server.services.geospatial.providers.base import (
    GeospatialProvider,
    ProviderRequest,
    ProviderResponse,
    ProviderUnavailableError,
)
from server.services.geospatial.providers.http import (
    JsonFetcher,
    call_json_fetcher,
    fetch_json_url,
)


class NOAAProvider(GeospatialProvider):
    provider_id = "noaa"

    def __init__(self, *, fetcher: JsonFetcher | None = None) -> None:
        self.fetcher = fetcher or fetch_json_url

    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        if request.capability_id == "noaa_coops_water_levels":
            return self._coops_water_levels(request)
        if request.capability_id == "noaa_radar":
            return self._radar_tiles(request)
        return await self._weather_alerts(request)

    async def _weather_alerts(self, request: ProviderRequest) -> ProviderResponse:
        params: dict[str, str] = {"status": "actual", "message_type": "alert"}
        if request.bbox is not None:
            west, south, east, north = request.bbox
            params["point"] = f"{(south + north) / 2},{(west + east) / 2}"
        features_url = f"https://api.weather.gov/alerts/active?{urlencode(params)}"
        if request.params.get("live"):
            payload = await call_json_fetcher(
                self.fetcher,
                features_url,
                {"User-Agent": "AEGIS-Geospatial-View/1.0"},
            )
            features = _normalize_noaa_alerts(payload)
            return ProviderResponse(
                capability_id=request.capability_id,
                provider_id=self.provider_id,
                payload={
                    "renderingMode": "geojson",
                    "features": features,
                    "totalResults": len(features),
                    "format": "geojson",
                    "legend": {"type": "alert-severity", "label": "NWS alert severity"},
                    "freshnessLabel": "NOAA active alerts feed",
                },
                attribution=["NOAA National Weather Service"],
            )
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={
                "renderingMode": "geojson",
                "featuresUrl": features_url,
                "format": "geojson",
                "legend": {"type": "alert-severity", "label": "NWS alert severity"},
                "freshnessLabel": "NOAA active alerts feed",
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
                "legend": {"type": "radar-reflectivity", "label": "Radar reflectivity"},
                "freshnessLabel": "NOAA/NCEP radar layer",
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
                "legend": {"type": "water-level", "label": "Observed water level"},
                "freshnessLabel": "NOAA CO-OPS water-level observations",
            },
            attribution=["NOAA CO-OPS"],
        )


def _normalize_noaa_alerts(payload: object) -> list[dict[str, object]]:
    if not isinstance(payload, dict):
        raise ProviderUnavailableError("NOAA alert payload must be a GeoJSON object.")
    raw_features = payload.get("features")
    if not isinstance(raw_features, list):
        raise ProviderUnavailableError("NOAA alert payload is missing features.")
    features: list[dict[str, object]] = []
    for item in raw_features:
        if not isinstance(item, dict):
            continue
        properties = item.get("properties") if isinstance(item.get("properties"), dict) else {}
        geometry = item.get("geometry") if isinstance(item.get("geometry"), dict) else None
        features.append(
            {
                "id": str(item.get("id") or properties.get("id") or ""),
                "name": properties.get("event") or properties.get("headline"),
                "category": "weather_alert",
                "severity": properties.get("severity"),
                "certainty": properties.get("certainty"),
                "urgency": properties.get("urgency"),
                "areaDescription": properties.get("areaDesc"),
                "effective": properties.get("effective"),
                "expires": properties.get("expires"),
                "geometry": geometry,
                "metadata": {
                    "sender": properties.get("senderName"),
                    "instruction": properties.get("instruction"),
                    "description": properties.get("description"),
                },
            }
        )
    return features
