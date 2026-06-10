from __future__ import annotations

import os
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
class OpenTripMapProvider(GeospatialProvider):
    provider_id = "opentripmap"

    # -------------------------------------------------------------------------
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

    # -------------------------------------------------------------------------
    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        api_key = (self.api_key or os.getenv("OPENTRIPMAP_API_KEY") or "").strip()
        if not api_key:
            raise ProviderAuthError("OPENTRIPMAP_API_KEY is required for OpenTripMap tourism POIs.")
        latitude, longitude = request_center(request)
        radius_m = request_radius_m(request, 2500.0)
        params = {
            "apikey": api_key,
            "lat": f"{latitude:.6f}",
            "lon": f"{longitude:.6f}",
            "radius": str(int(radius_m)),
            "format": "geojson",
            "limit": str(int(request.params.get("limit") or 100)),
            "kinds": str(request.params.get("kinds") or "interesting_places"),
        }
        url = f"https://api.opentripmap.com/0.1/en/places/radius?{urlencode(params)}"
        if not bool(request.params.get("live")):
            return ProviderResponse(
                capability_id=request.capability_id,
                provider_id=self.provider_id,
                payload={
                    "renderingMode": "clustered-points",
                    "featuresUrl": url,
                },
                attribution=["OpenTripMap"],
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
                attribution=["OpenTripMap"],
            )
        except (ProviderError, ValueError) as exc:
            cached = self.cache.get(cache_key)
            if cached.status == CacheLookupStatus.STALE and isinstance(cached.value, dict):
                return ProviderResponse(
                    capability_id=request.capability_id,
                    provider_id=self.provider_id,
                    payload=cached.value,
                    attribution=["OpenTripMap"],
                    warnings=["OpenTripMap request failed; serving stale cached POIs."],
                    stale=True,
                )
            if isinstance(exc, ProviderError):
                raise
            raise ProviderUnavailableError(str(exc)) from exc

    # -------------------------------------------------------------------------
    def _features(self, payload: object) -> list[dict[str, object]]:
        if not isinstance(payload, dict):
            raise ValueError("OpenTripMap payload must be an object.")
        raw_features = payload.get("features")
        if not isinstance(raw_features, list):
            return []
        features: list[dict[str, object]] = []
        for item in raw_features:
            if not isinstance(item, dict):
                continue
            geometry = item.get("geometry")
            properties = item.get("properties")
            if not isinstance(geometry, dict) or not isinstance(properties, dict):
                continue
            coordinates = geometry.get("coordinates")
            if not isinstance(coordinates, list) or len(coordinates) < 2:
                continue
            category = normalize_poi_category(str(properties.get("kinds") or "tourism").split(",")[0])
            features.append(
                {
                    "id": str(properties.get("xid") or properties.get("id") or ""),
                    "name": properties.get("name"),
                    "category": category,
                    "source": self.provider_id,
                    "latitude": coordinates[1],
                    "longitude": coordinates[0],
                    "metadata": {
                        "kinds": properties.get("kinds"),
                        "wikidata": properties.get("wikidata"),
                    },
                }
            )
        return features
