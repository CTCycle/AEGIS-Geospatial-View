from __future__ import annotations

from typing import Any

from server.common.constants import GIBS_WMS_BASE_ENDPOINTS, NASA_ATTRIBUTION
from server.services.geospatial.cache import CacheLookupStatus, GeospatialCache
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


class NASAGIBSProvider(GeospatialProvider):
    provider_id = "gibs"

    def __init__(
        self,
        *,
        fetcher: JsonFetcher | None = None,
        cache: GeospatialCache | None = None,
        cache_ttl_seconds: int = 3600,
        stale_while_revalidate_seconds: int = 86400,
    ) -> None:
        self.fetcher = fetcher or fetch_json_url
        self.cache = cache or GeospatialCache()
        self.cache_ttl_seconds = cache_ttl_seconds
        self.stale_while_revalidate_seconds = stale_while_revalidate_seconds

    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        crs = str(request.params.get("crs") or "EPSG:3857")
        endpoint = GIBS_WMS_BASE_ENDPOINTS.get(crs, GIBS_WMS_BASE_ENDPOINTS["EPSG:3857"])
        layer = str(request.params.get("layer") or request.capability_id)
        time_value = request.params.get("time")
        payload: dict[str, Any] = {
            "renderingMode": "wms",
            "serviceUrl": endpoint,
            "layers": [layer],
            "crs": crs,
            "time": time_value,
            "format": str(request.params.get("format") or "image/png"),
        }
        if request.params.get("live_validate"):
            return await self._validated_response(request, payload)
        return self._response(request, payload)

    async def _validated_response(
        self, request: ProviderRequest, payload: dict[str, Any]
    ) -> ProviderResponse:
        service_url = str(payload.get("serviceUrl") or "").strip()
        cache_key = f"{self.provider_id}:{request.capability_id}:{service_url}"
        cached = self.cache.get(cache_key)
        if cached.status == CacheLookupStatus.HIT and isinstance(cached.value, dict):
            return self._response(request, {**payload, "liveValidation": cached.value})
        try:
            validation = await call_json_fetcher(self.fetcher, service_url, None)
        except Exception as exc:
            if cached.status == CacheLookupStatus.STALE and isinstance(cached.value, dict):
                return self._response(
                    request,
                    {**payload, "liveValidation": cached.value},
                    stale=True,
                    warnings=["NASA GIBS descriptor validation failed; using stale validation metadata."],
                )
            if isinstance(exc, ProviderUnavailableError):
                raise
            raise ProviderUnavailableError("NASA GIBS descriptor validation failed.") from exc
        if not isinstance(validation, dict):
            if cached.status == CacheLookupStatus.STALE and isinstance(cached.value, dict):
                return self._response(
                    request,
                    {**payload, "liveValidation": cached.value},
                    stale=True,
                    warnings=["NASA GIBS descriptor validation was malformed; using stale validation metadata."],
                )
            raise ProviderUnavailableError("NASA GIBS descriptor validation returned malformed metadata.")
        self.cache.set(
            cache_key,
            validation,
            ttl_seconds=self.cache_ttl_seconds,
            stale_while_revalidate_seconds=self.stale_while_revalidate_seconds,
        )
        return self._response(request, {**payload, "liveValidation": validation})

    def _response(
        self,
        request: ProviderRequest,
        payload: dict[str, Any],
        *,
        stale: bool = False,
        warnings: list[str] | None = None,
    ) -> ProviderResponse:
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload=payload,
            attribution=[NASA_ATTRIBUTION],
            warnings=warnings or [],
            stale=stale,
        )
