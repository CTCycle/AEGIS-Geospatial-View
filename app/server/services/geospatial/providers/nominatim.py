from __future__ import annotations

from urllib.parse import urlencode

from server.services.geospatial.cache import CacheLookupStatus, GeospatialCache
from server.services.geospatial.providers.base import (
    GeospatialProvider,
    ProviderError,
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
class NominatimProvider(GeospatialProvider):
    provider_id = "nominatim"

    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        fetcher: JsonFetcher | None = None,
        cache: GeospatialCache | None = None,
    ) -> None:
        self.fetcher = fetcher or fetch_json_url
        self.cache = cache or GeospatialCache()

    # -------------------------------------------------------------------------
    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        query = str(request.params.get("query") or request.params.get("q") or "").strip()
        if not query:
            return ProviderResponse(
                capability_id=request.capability_id,
                provider_id=self.provider_id,
                payload={
                    "renderingMode": "metadata-only",
                    "status": "location-query-needed",
                    "message": "Provide a location query before geocoding.",
                },
                attribution=["OpenStreetMap contributors", "Nominatim"],
            )
        url = self._url(query)
        cache_key = f"{self.provider_id}:{url}"
        try:
            payload = await call_json_fetcher(
                self.fetcher,
                url,
                {"User-Agent": "AEGIS-Geospatial-View/1.0"},
            )
            normalized = self._normalize(payload, query=query)
            self.cache.set(cache_key, normalized, ttl_seconds=3600, stale_while_revalidate_seconds=86400)
            return ProviderResponse(
                capability_id=request.capability_id,
                provider_id=self.provider_id,
                payload=normalized,
                attribution=["OpenStreetMap contributors", "Nominatim"],
            )
        except ProviderError:
            cached = self.cache.get(cache_key)
            if cached.status == CacheLookupStatus.STALE and isinstance(cached.value, dict):
                return ProviderResponse(
                    capability_id=request.capability_id,
                    provider_id=self.provider_id,
                    payload=cached.value,
                    attribution=["OpenStreetMap contributors", "Nominatim"],
                    warnings=["Nominatim request failed; serving stale geocode result."],
                    stale=True,
                )
            raise

    # -------------------------------------------------------------------------
    async def fetch_features(self, request: ProviderRequest) -> ProviderResponse:
        return await self.fetch(request)

    # -------------------------------------------------------------------------
    def _url(self, query: str) -> str:
        params = {
            "q": query,
            "format": "jsonv2",
            "limit": "5",
            "addressdetails": "1",
        }
        return f"https://nominatim.openstreetmap.org/search?{urlencode(params)}"

    # -------------------------------------------------------------------------
    def _normalize(self, payload: object, *, query: str) -> dict[str, object]:
        if not isinstance(payload, list):
            raise ProviderMalformedPayloadError("Nominatim search payload must be a list.")
        results = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            lat = self._float_or_none(item.get("lat"))
            lon = self._float_or_none(item.get("lon"))
            if lat is None or lon is None:
                continue
            results.append(
                {
                    "id": item.get("place_id") or item.get("osm_id"),
                    "name": item.get("display_name") or item.get("name"),
                    "latitude": lat,
                    "longitude": lon,
                    "bbox": item.get("boundingbox"),
                    "category": item.get("category"),
                    "type": item.get("type"),
                    "importance": item.get("importance"),
                }
            )
        return {
            "renderingMode": "metadata-only",
            "query": query,
            "results": results,
            "resultCount": len(results),
        }

    # -------------------------------------------------------------------------
    def _float_or_none(self, value: object) -> float | None:
        try:
            return float(str(value))
        except (TypeError, ValueError):
            return None
