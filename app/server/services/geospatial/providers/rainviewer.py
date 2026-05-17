from __future__ import annotations

from typing import Any

from server.services.geospatial.cache import CacheLookupStatus, GeospatialCache
from server.services.geospatial.providers.base import (
    GeospatialProvider,
    ProviderRequest,
    ProviderResponse,
)
from server.services.geospatial.rainviewer import RainViewerService, RainViewerServiceError


class RainViewerProvider(GeospatialProvider):
    provider_id = "rainviewer"

    def __init__(
        self,
        *,
        service: RainViewerService | None = None,
        cache: GeospatialCache | None = None,
        cache_ttl_seconds: int = 300,
        stale_while_revalidate_seconds: int = 3600,
    ) -> None:
        self.service = service or RainViewerService()
        self.cache = cache or GeospatialCache()
        self.cache_ttl_seconds = cache_ttl_seconds
        self.stale_while_revalidate_seconds = stale_while_revalidate_seconds

    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        cache_key = f"{self.provider_id}:latest-radar"
        cached = self.cache.get(cache_key)
        if cached.status == CacheLookupStatus.HIT and isinstance(cached.value, dict):
            return self._response(request, cached.value)
        try:
            metadata = await self.service.get_latest_radar_metadata()
        except RainViewerServiceError as exc:
            if cached.status == CacheLookupStatus.STALE and isinstance(cached.value, dict):
                return self._response(
                    request,
                    cached.value,
                    stale=True,
                    warnings=[
                        "RainViewer metadata refresh failed; using stale cached radar frame."
                    ],
                )
            return self._empty_response(
                request,
                warning=f"RainViewer metadata could not be fetched: {exc}",
            )
        if not self._is_usable_metadata(metadata):
            if cached.status == CacheLookupStatus.STALE and isinstance(cached.value, dict):
                return self._response(
                    request,
                    cached.value,
                    stale=True,
                    warnings=[
                        "RainViewer metadata was malformed; using stale cached radar frame."
                    ],
                )
            return self._empty_response(
                request,
                warning="RainViewer metadata did not include a usable radar tile frame.",
            )
        self.cache.set(
            cache_key,
            metadata,
            ttl_seconds=self.cache_ttl_seconds,
            stale_while_revalidate_seconds=self.stale_while_revalidate_seconds,
        )
        return self._response(request, metadata)

    def _response(
        self,
        request: ProviderRequest,
        metadata: dict[str, Any],
        *,
        stale: bool = False,
        warnings: list[str] | None = None,
    ) -> ProviderResponse:
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={
                "renderingMode": "raster-tile",
                "tileUrl": metadata.get("tile_url_template"),
                "latestTime": metadata.get("latest_time"),
                "frameCount": metadata.get("frame_count"),
                "resolvedAt": metadata.get("resolved_at"),
            },
            attribution=[str(metadata.get("attribution") or "© RainViewer")],
            warnings=warnings or [],
            stale=stale,
        )

    def _empty_response(self, request: ProviderRequest, *, warning: str) -> ProviderResponse:
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={
                "renderingMode": "raster-tile",
                "status": "empty",
                "tileUrl": None,
                "latestTime": None,
                "frameCount": 0,
                "resolvedAt": None,
            },
            attribution=["© RainViewer"],
            warnings=[warning],
        )

    def _is_usable_metadata(self, metadata: dict[str, Any]) -> bool:
        tile_url = str(metadata.get("tile_url_template") or "").strip()
        latest_time = metadata.get("latest_time")
        return bool(tile_url and latest_time)
