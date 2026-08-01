from __future__ import annotations

from server.common.typing import is_json_array, is_json_object, json_array, json_object

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

###############################################################################
class USGSProvider(GeospatialProvider):
    provider_id = "usgs"

    # -------------------------------------------------------------------------
    def __init__(self, *, fetcher: JsonFetcher | None = None) -> None:
        self.fetcher = fetcher or fetch_json_url

    # -------------------------------------------------------------------------
    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        if request.capability_id == "usgs_water_gauges":
            return await self._water_services(request)
        return await self._earthquakes(request)

    # -------------------------------------------------------------------------
    async def _earthquakes(self, request: ProviderRequest) -> ProviderResponse:
        feed = str(request.params.get("feed") or "all_day").strip()
        features_url = f"https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/{feed}.geojson"
        if request.params.get("live"):
            payload = await call_json_fetcher(self.fetcher, features_url)
            features = _normalize_earthquake_features(payload)
            return ProviderResponse(
                capability_id=request.capability_id,
                provider_id=self.provider_id,
                payload={
                    "renderingMode": "clustered-points",
                    "features": features,
                    "totalResults": len(features),
                    "timeMode": "current",
                    "legend": {"type": "magnitude", "label": "Earthquake magnitude"},
                    "freshnessLabel": "USGS all-day earthquake feed",
                },
                attribution=["U.S. Geological Survey"],
            )
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={
                "renderingMode": "clustered-points",
                "featuresUrl": features_url,
                "timeMode": "current",
                "legend": {"type": "magnitude", "label": "Earthquake magnitude"},
                "freshnessLabel": "USGS all-day earthquake feed",
            },
            attribution=["U.S. Geological Survey"],
        )

    # -------------------------------------------------------------------------
    async def _water_services(self, request: ProviderRequest) -> ProviderResponse:
        params = {
            "format": "json",
            "siteStatus": "active",
            "parameterCd": request.params.get("parameterCd") or "00065",
        }
        if request.bbox is not None:
            west, south, east, north = request.bbox
            params["bBox"] = f"{west},{south},{east},{north}"
        features_url = f"https://waterservices.usgs.gov/nwis/iv/?{urlencode(params)}"
        if request.params.get("live"):
            payload = await call_json_fetcher(self.fetcher, features_url)
            features = _normalize_water_gauge_features(payload)
            return ProviderResponse(
                capability_id=request.capability_id,
                provider_id=self.provider_id,
                payload={
                    "renderingMode": "clustered-points",
                    "features": features,
                    "totalResults": len(features),
                    "format": "json",
                    "legend": {"type": "water-level", "label": "Latest gauge observation"},
                    "freshnessLabel": "USGS instantaneous values feed",
                },
                attribution=["U.S. Geological Survey"],
            )
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={
                "renderingMode": "clustered-points",
                "featuresUrl": features_url,
                "format": "json",
                "legend": {"type": "water-level", "label": "Latest gauge observation"},
                "freshnessLabel": "USGS instantaneous values feed",
            },
            attribution=["U.S. Geological Survey"],
        )

###############################################################################
def _normalize_earthquake_features(payload: object) -> list[dict[str, object]]:
    if not is_json_object(payload):
        raise ProviderUnavailableError("USGS earthquake payload must be a GeoJSON object.")
    raw_features = payload.get("features")
    if not is_json_array(raw_features):
        raise ProviderUnavailableError("USGS earthquake payload is missing features.")
    features: list[dict[str, object]] = []
    for item in raw_features:
        if not is_json_object(item):
            continue
        properties = json_object(item.get("properties"))
        geometry = json_object(item.get("geometry"))
        coordinates = geometry.get("coordinates")
        if not is_json_array(coordinates) or len(coordinates) < 2:
            continue
        longitude, latitude = coordinates[0], coordinates[1]
        if not isinstance(latitude, int | float) or not isinstance(longitude, int | float):
            continue
        features.append(
            {
                "id": str(item.get("id") or properties.get("code") or ""),
                "name": properties.get("place"),
                "category": "earthquake",
                "latitude": float(latitude),
                "longitude": float(longitude),
                "magnitude": properties.get("mag"),
                "time": properties.get("time"),
                "url": properties.get("url"),
                "metadata": {
                    "status": properties.get("status"),
                    "type": properties.get("type"),
                    "tsunami": properties.get("tsunami"),
                },
            }
        )
    return features

###############################################################################
def _normalize_water_gauge_features(payload: object) -> list[dict[str, object]]:
    if not is_json_object(payload):
        raise ProviderUnavailableError("USGS water-services payload must be an object.")
    value = json_object(payload.get("value"))
    raw_series = json_array(value.get("timeSeries"))
    features: list[dict[str, object]] = []
    for series in raw_series:
        if not is_json_object(series):
            continue
        source_info = json_object(series.get("sourceInfo"))
        geo = json_object(source_info.get("geoLocation"))
        geog = json_object(geo.get("geogLocation"))
        latitude = geog.get("latitude")
        longitude = geog.get("longitude")
        if not isinstance(latitude, int | float) or not isinstance(longitude, int | float):
            continue
        values = json_array(series.get("values"))
        latest_value = _latest_usgs_value(values)
        site_codes = json_array(source_info.get("siteCode"))
        first_site_code = json_object(site_codes[0]) if site_codes else {}
        features.append(
            {
                "id": first_site_code.get("value") or source_info.get("siteName"),
                "name": source_info.get("siteName"),
                "category": "water_gauge",
                "latitude": float(latitude),
                "longitude": float(longitude),
                "value": latest_value.get("value"),
                "timestamp": latest_value.get("dateTime"),
                "metadata": {
                    "variable": (
                        series.get("variable", {}).get("variableName")
                        if is_json_object(series.get("variable"))
                        else None
                    ),
                    "unit": _unit_code(series),
                },
            }
        )
    return features

###############################################################################
def _latest_usgs_value(values: list[object]) -> dict[str, object]:
    if not values or not is_json_object(values[0]):
        return {}
    entries = values[0].get("value")
    if not is_json_array(entries) or not entries:
        return {}
    latest = entries[-1]
    return json_object(latest)

###############################################################################
def _unit_code(series: dict[str, object]) -> object:
    variable = json_object(series.get("variable"))
    unit = json_object(variable.get("unit"))
    return unit.get("unitCode")
