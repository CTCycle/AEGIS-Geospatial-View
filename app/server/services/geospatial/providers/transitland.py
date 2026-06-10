from __future__ import annotations

from urllib.parse import urlencode

from server.services.geospatial.cache import CacheLookupStatus, GeospatialCache
from server.services.geospatial.providers.base import (
    ProviderAuthError,
    ProviderError,
    ProviderRequest,
    ProviderResponse,
)
from server.services.geospatial.providers.http import (
    JsonFetcher,
    call_json_fetcher,
    fetch_json_url,
)


###############################################################################
class TransitlandProvider:
    provider_id = "transitland"

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
        if not self.api_key:
            raise ProviderAuthError("Transitland access requires a configured API key.")
        url = self._url(request)
        cache_key = f"{self.provider_id}:{url}"
        try:
            payload = await call_json_fetcher(
                self.fetcher,
                url,
                {"apikey": self.api_key, "Accept": "application/json"},
            )
            normalized = self._normalize(payload)
            normalized["queryUrl"] = url
            self.cache.set(
                cache_key,
                normalized,
                ttl_seconds=86400,
                stale_while_revalidate_seconds=604800,
            )
            return ProviderResponse(
                capability_id=request.capability_id,
                provider_id=self.provider_id,
                payload=normalized,
                attribution=["Transitland"],
            )
        except ProviderError:
            cached = self.cache.get(cache_key)
            if cached.status == CacheLookupStatus.STALE and isinstance(cached.value, dict):
                return ProviderResponse(
                    capability_id=request.capability_id,
                    provider_id=self.provider_id,
                    payload=cached.value,
                    attribution=["Transitland"],
                    warnings=["Transitland request failed; serving stale feed discovery results."],
                    stale=True,
                )
            raise

    # -------------------------------------------------------------------------
    async def fetch_features(self, request: ProviderRequest) -> ProviderResponse:
        return await self.fetch(request)

    # -------------------------------------------------------------------------
    def _url(self, request: ProviderRequest) -> str:
        params: dict[str, str] = {
            "limit": str(int(request.params.get("limit") or 50)),
        }
        query = str(request.params.get("query") or "").strip()
        if query:
            params["q"] = query
        if request.bbox:
            west, south, east, north = request.bbox
            params["bbox"] = f"{west},{south},{east},{north}"
        return f"https://transit.land/api/v2/rest/feeds?{urlencode(params)}"

    # -------------------------------------------------------------------------
    def _normalize(self, payload: object) -> dict[str, object]:
        if not isinstance(payload, dict):
            return {"renderingMode": "metadata-only", "feeds": [], "feedCount": 0}
        raw_feeds = payload.get("feeds") or payload.get("data") or []
        feeds = [self._feed(item) for item in raw_feeds if isinstance(item, dict)]
        return {
            "renderingMode": "metadata-only",
            "type": "search-index",
            "feeds": feeds,
            "feedCount": len(feeds),
        }

    # -------------------------------------------------------------------------
    def _feed(self, item: dict[str, object]) -> dict[str, object]:
        urls = item.get("urls") if isinstance(item.get("urls"), dict) else {}
        operator = item.get("operator") if isinstance(item.get("operator"), dict) else {}
        return {
            "id": item.get("id") or item.get("onestop_id"),
            "name": item.get("name") or operator.get("name"),
            "operator": operator.get("name"),
            "staticFeedUrl": urls.get("static_current") or urls.get("static"),
            "realtimeVehiclePositionsUrl": urls.get("realtime_vehicle_positions"),
            "realtimeTripUpdatesUrl": urls.get("realtime_trip_updates"),
            "realtimeAlertsUrl": urls.get("realtime_alerts"),
            "license": item.get("license"),
        }
