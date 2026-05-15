from __future__ import annotations

from typing import Any

from server.services.geospatial.cache import CacheLookupStatus, GeospatialCache
from server.services.geospatial.providers.base import (
    GeospatialProvider,
    ProviderRequest,
    ProviderResponse,
    ProviderUnavailableError,
)
from server.services.geospatial.providers.http import JsonFetcher, call_json_fetcher, fetch_json_url


class ESAProvider(GeospatialProvider):
    provider_id = "esa"

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
        metadata = _metadata(request)
        payload = self._descriptor_payload(request, metadata)
        if request.params.get("live_validate"):
            return await self._validated_response(request, metadata, payload)
        return self._response(request, metadata, payload)

    def _descriptor_payload(
        self, request: ProviderRequest, metadata: dict[str, Any]
    ) -> dict[str, Any]:
        return {
            "renderingMode": "wmts",
            "serviceUrl": metadata.get("url"),
            "layerId": metadata.get("layer_id") or request.capability_id,
            "tileMatrixSet": metadata.get("tile_matrix_set") or "EPSG:3857",
            "format": metadata.get("wmts_format") or "image/png",
            "style": metadata.get("wmts_style") or "",
            "legend": {
                "title": metadata.get("label") or "ESA WorldCover",
                "source": "ESA WorldCover / Terrascope",
            },
            "freshnessLabel": "WorldCover 2021 static source layer",
        }

    async def _validated_response(
        self,
        request: ProviderRequest,
        metadata: dict[str, Any],
        payload: dict[str, Any],
    ) -> ProviderResponse:
        service_url = str(payload.get("serviceUrl") or "").strip()
        cache_key = f"{self.provider_id}:{request.capability_id}:{service_url}"
        cached = self.cache.get(cache_key)
        if cached.status == CacheLookupStatus.HIT and isinstance(cached.value, dict):
            return self._response(request, metadata, {**payload, "liveValidation": cached.value})
        try:
            validation = await call_json_fetcher(self.fetcher, service_url, None)
        except Exception as exc:
            if cached.status == CacheLookupStatus.STALE and isinstance(cached.value, dict):
                return self._response(
                    request,
                    metadata,
                    {**payload, "liveValidation": cached.value},
                    stale=True,
                    warnings=["ESA WMTS validation failed; using stale validation metadata."],
                )
            if isinstance(exc, ProviderUnavailableError):
                raise
            raise ProviderUnavailableError("ESA WMTS validation failed.") from exc
        if not isinstance(validation, dict):
            if cached.status == CacheLookupStatus.STALE and isinstance(cached.value, dict):
                return self._response(
                    request,
                    metadata,
                    {**payload, "liveValidation": cached.value},
                    stale=True,
                    warnings=["ESA WMTS validation was malformed; using stale validation metadata."],
                )
            raise ProviderUnavailableError("ESA WMTS validation returned malformed metadata.")
        self.cache.set(
            cache_key,
            validation,
            ttl_seconds=self.cache_ttl_seconds,
            stale_while_revalidate_seconds=self.stale_while_revalidate_seconds,
        )
        return self._response(request, metadata, {**payload, "liveValidation": validation})

    def _response(
        self,
        request: ProviderRequest,
        metadata: dict[str, Any],
        payload: dict[str, Any],
        *,
        stale: bool = False,
        warnings: list[str] | None = None,
    ) -> ProviderResponse:
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload=payload,
            attribution=[str(metadata.get("attribution") or "ESA WorldCover")],
            warnings=warnings or [],
            stale=stale,
        )


def _metadata(request: ProviderRequest) -> dict[str, Any]:
    value = request.params.get("metadata")
    return dict(value) if isinstance(value, dict) else {}
