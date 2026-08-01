from __future__ import annotations

from server.common.typing import is_json_array, is_json_object, json_array, json_object

import os
import json
from pathlib import Path
from urllib.parse import urlencode

from server.services.geospatial.cache import CacheLookupStatus, GeospatialCache
from server.services.geospatial.normalizers import normalize_poi_category
from server.services.geospatial.providers._request import (
    request_center,
    request_radius_m,
)
from server.services.geospatial.providers.base import (
    GeospatialProvider,
    ProviderAuthError,
    ProviderError,
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
class OpenChargeMapProvider(GeospatialProvider):
    provider_id = "openchargemap"

    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        api_key: str | None = None,
        fetcher: JsonFetcher | None = None,
        cache: GeospatialCache | None = None,
        snapshot_path: str | Path | None = None,
    ) -> None:
        self.api_key = api_key
        self.fetcher = fetcher or fetch_json_url
        self.cache = cache or GeospatialCache()
        self.snapshot_path = Path(snapshot_path or os.getenv("AEGIS_OCM_SNAPSHOT_PATH", "")).expanduser() if (snapshot_path or os.getenv("AEGIS_OCM_SNAPSHOT_PATH", "").strip()) else None

    # -------------------------------------------------------------------------
    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        latitude, longitude = request_center(request)
        radius_m = request_radius_m(request, 10000.0)
        params = {
            "output": "json",
            "latitude": f"{latitude:.6f}",
            "longitude": f"{longitude:.6f}",
            "distance": f"{radius_m / 1000:.1f}",
            "distanceunit": "KM",
            "maxresults": str(int(request.params.get("maxresults") or 100)),
        }
        api_key = (self.api_key or os.getenv("OPENCHARGEMAP_API_KEY") or "").strip()
        snapshot = request.params.get("snapshot_path") or self.snapshot_path
        if snapshot:
            snapshot_path = Path(str(snapshot)).expanduser()
            if snapshot_path.is_file():
                try:
                    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
                except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                    raise ProviderUnavailableError("Open Charge Map snapshot is unavailable or malformed.") from exc
                features = self._features(payload)
                filtered = _filter_features(features, request, latitude, longitude, radius_m)
                return ProviderResponse(
                    capability_id=request.capability_id,
                    provider_id=self.provider_id,
                    payload={
                        "renderingMode": "clustered-points",
                        "sourceMode": "local-snapshot",
                        "snapshotPath": str(snapshot_path),
                        "features": filtered,
                        "featureCount": len(filtered),
                        "center": {"latitude": latitude, "longitude": longitude},
                        "radiusM": radius_m,
                    },
                    attribution=["Open Charge Map"],
                )
            raise ProviderUnavailableError("Configured Open Charge Map snapshot does not exist.")
        if not api_key:
            raise ProviderAuthError(
                "Open Charge Map hosted API access requires OPENCHARGEMAP_API_KEY; configure a local snapshot for anonymous operation."
            )
        params["key"] = api_key
        url = f"https://api.openchargemap.io/v3/poi/?{urlencode(params)}"
        if not bool(request.params.get("live")):
            return ProviderResponse(
                capability_id=request.capability_id,
                provider_id=self.provider_id,
                payload={
                    "renderingMode": "clustered-points",
                    "featuresUrl": url,
                },
                attribution=["Open Charge Map"],
            )
        cache_key = f"{self.provider_id}:{url}"
        try:
            payload = await call_json_fetcher(self.fetcher, url, None)
            features = self._features(payload)
            normalized = {
                "renderingMode": "clustered-points",
                "features": features,
                "featureCount": len(features),
                "center": {"latitude": latitude, "longitude": longitude},
                "radiusM": radius_m,
            }
            self.cache.set(cache_key, normalized, ttl_seconds=900, stale_while_revalidate_seconds=86400)
            return ProviderResponse(
                capability_id=request.capability_id,
                provider_id=self.provider_id,
                payload=normalized,
                attribution=["Open Charge Map"],
            )
        except (ProviderError, ValueError) as exc:
            cached = self.cache.get(cache_key)
            if cached.status == CacheLookupStatus.STALE and is_json_object(cached.value):
                return ProviderResponse(
                    capability_id=request.capability_id,
                    provider_id=self.provider_id,
                    payload=cached.value,
                    attribution=["Open Charge Map"],
                    warnings=["Open Charge Map request failed; serving stale cached stations."],
                    stale=True,
                )
            if isinstance(exc, ProviderError):
                raise
            raise ProviderUnavailableError(str(exc)) from exc

    # -------------------------------------------------------------------------
    def _features(self, payload: object) -> list[dict[str, object]]:
        if is_json_object(payload) and payload.get("type") == "FeatureCollection":
            return _geojson_features(payload)
        if not is_json_array(payload):
            raise ValueError("Open Charge Map payload must be a list.")
        features: list[dict[str, object]] = []
        for item in json_array(payload):
            item = json_object(item)
            if not item:
                continue
            address = json_object(item.get("AddressInfo"))
            if not address:
                continue
            latitude = address.get("Latitude")
            longitude = address.get("Longitude")
            if not isinstance(latitude, int | float) or not isinstance(longitude, int | float):
                continue
            features.append(
                {
                    "id": str(item.get("ID") or ""),
                    "name": address.get("Title"),
                    "category": normalize_poi_category("ev_charging"),
                    "source": self.provider_id,
                    "latitude": float(str(latitude)),
                    "longitude": float(str(longitude)),
                    "address": address.get("AddressLine1"),
                    "metadata": {
                    "status": json_object(item.get("StatusType")).get("Title"),
                        "connections": item.get("Connections") or [],
                    },
                }
            )
        return features

###############################################################################
def _filter_features(
    features: list[dict[str, object]],
    request: ProviderRequest,
    latitude: float,
    longitude: float,
    radius_m: float,
) -> list[dict[str, object]]:
    del latitude, longitude, radius_m
    if request.bbox is None:
        return features[: int(request.params.get("maxresults") or 100)]
    west, south, east, north = request.bbox
    return [
        item
        for item in features
        if west <= float(str(item["longitude"])) <= east and south <= float(str(item["latitude"])) <= north
    ][: int(request.params.get("maxresults") or 100)]

###############################################################################
def _geojson_features(payload: dict[str, object]) -> list[dict[str, object]]:
    features: list[dict[str, object]] = []
    for feature in json_array(payload.get("features")):
        feature = json_object(feature)
        if not feature:
            continue
        geometry = json_object(feature.get("geometry"))
        properties = json_object(feature.get("properties"))
        coordinates = geometry.get("coordinates")
        if not is_json_array(coordinates) or len(coordinates) < 2:
            continue
        features.append({
            "id": str(feature.get("id") or properties.get("id") or ""),
            "name": properties.get("name"),
            "category": normalize_poi_category("ev_charging"),
            "source": "openchargemap",
            "latitude": float(str(coordinates[1])),
            "longitude": float(str(coordinates[0])),
            "address": properties.get("address"),
            "metadata": properties,
        })
    return features
