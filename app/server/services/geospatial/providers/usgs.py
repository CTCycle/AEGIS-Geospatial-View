from __future__ import annotations

from urllib.parse import urlencode

from server.common.typing import is_json_array, is_json_object, json_object

from server.services.geospatial.providers.base import (
    GeospatialProvider,
    ProviderMalformedPayloadError,
    ProviderRequest,
    ProviderResponse,
)
from server.services.geospatial.providers.http import (
    JsonFetcher,
    call_json_fetcher,
    fetch_json_url,
)

###############################################################################
class USGSProvider(GeospatialProvider):
    provider_id = "usgs"
    WATER_DATA_ITEMS_URL = (
        "https://api.waterdata.usgs.gov/ogcapi/v0/collections/"
        "latest-continuous/items"
    )

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
                result_status="valid_empty" if not features else "ok",
                result_type="features",
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
            result_type="metadata",
        )

    # -------------------------------------------------------------------------
    async def _water_services(self, request: ProviderRequest) -> ProviderResponse:
        params: dict[str, str | int] = {
            "f": "json",
            "limit": max(1, min(int(request.params.get("limit") or 1000), 10000)),
            "parameter_code": str(request.params.get("parameterCd") or "00065"),
        }
        if request.bbox is not None:
            west, south, east, north = request.bbox
            params["bbox"] = f"{west},{south},{east},{north}"
        features_url = f"{self.WATER_DATA_ITEMS_URL}?{urlencode(params)}"
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
                    "format": "geojson",
                    "legend": {"type": "water-level", "label": "Latest gauge observation"},
                    "freshnessLabel": "USGS latest-continuous observations",
                },
                attribution=["U.S. Geological Survey"],
                result_status="valid_empty" if not features else "ok",
                result_type="features",
            )
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={
                "renderingMode": "clustered-points",
                "featuresUrl": features_url,
                "format": "geojson",
                "legend": {"type": "water-level", "label": "Latest gauge observation"},
                "freshnessLabel": "USGS latest-continuous observations",
            },
            attribution=["U.S. Geological Survey"],
            result_type="metadata",
        )

###############################################################################
def _normalize_earthquake_features(payload: object) -> list[dict[str, object]]:
    if not is_json_object(payload):
        raise ProviderMalformedPayloadError("USGS earthquake payload must be a GeoJSON object.")
    raw_features = payload.get("features")
    if not is_json_array(raw_features):
        raise ProviderMalformedPayloadError("USGS earthquake payload is missing features.")
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
    if not is_json_object(payload) or payload.get("type") != "FeatureCollection":
        raise ProviderMalformedPayloadError(
            "USGS latest-continuous payload must be a GeoJSON FeatureCollection."
        )
    raw_features = payload.get("features")
    if not is_json_array(raw_features):
        raise ProviderMalformedPayloadError(
            "USGS latest-continuous payload is missing features."
        )
    features: list[dict[str, object]] = []
    for raw_feature in raw_features:
        feature = json_object(raw_feature)
        geometry = json_object(feature.get("geometry"))
        properties = json_object(feature.get("properties"))
        coordinates = geometry.get("coordinates")
        if not is_json_array(coordinates) or len(coordinates) < 2:
            continue
        longitude, latitude = coordinates[0], coordinates[1]
        value = _float_or_none(properties.get("value"))
        if (
            not isinstance(latitude, int | float)
            or not isinstance(longitude, int | float)
            or value is None
        ):
            continue
        station_id = (
            properties.get("monitoring_location_id")
            or properties.get("monitoringLocationId")
            or feature.get("id")
        )
        features.append(
            {
                "id": str(station_id or ""),
                "name": properties.get("monitoring_location_name")
                or properties.get("name")
                or station_id,
                "category": "water_gauge",
                "latitude": float(latitude),
                "longitude": float(longitude),
                "value": value,
                "timestamp": properties.get("time"),
                "metadata": {
                    "parameterCode": properties.get("parameter_code"),
                    "unit": properties.get("unit_of_measure"),
                    "observedProperty": properties.get("observed_property"),
                    "verticalDatum": properties.get("vertical_datum"),
                    "huc": properties.get("huc"),
                },
            }
        )
    return features

###############################################################################
def _float_or_none(value: object) -> float | None:
    if not isinstance(value, int | float | str):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
