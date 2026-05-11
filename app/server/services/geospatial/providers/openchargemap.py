from __future__ import annotations

import os
from urllib.parse import urlencode

from server.services.geospatial.cache import CacheLookupStatus, GeospatialCache
from server.services.geospatial.normalizers import normalize_poi_category
from server.services.geospatial.providers._request import request_center, request_radius_m
from server.services.geospatial.providers.base import (
    GeospatialProvider,
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


class OpenChargeMapProvider(GeospatialProvider):
    provider_id = "openchargemap"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        fetcher: JsonFetcher | None = None,
        cache: GeospatialCache | None = None,
    ) -> None:
        self.api_key = api_key
        self.fetcher = fetcher or fetch_json_url
        self.cache = cache or GeospatialCache()

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
        if api_key:
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
            if cached.status == CacheLookupStatus.STALE and isinstance(cached.value, dict):
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

    def _features(self, payload: object) -> list[dict[str, object]]:
        if not isinstance(payload, list):
            raise ValueError("Open Charge Map payload must be a list.")
        features: list[dict[str, object]] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            address = item.get("AddressInfo")
            if not isinstance(address, dict):
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
                    "latitude": float(latitude),
                    "longitude": float(longitude),
                    "address": address.get("AddressLine1"),
                    "metadata": {
                        "status": (item.get("StatusType") or {}).get("Title")
                        if isinstance(item.get("StatusType"), dict)
                        else None,
                        "connections": item.get("Connections") or [],
                    },
                }
            )
        return features
