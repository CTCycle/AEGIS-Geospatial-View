from __future__ import annotations

from typing import Any

from server.common.typing import is_json_object
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

###############################################################################
class ESAProvider(GeospatialProvider):
    provider_id = "esa"

    # -------------------------------------------------------------------------
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

    # -------------------------------------------------------------------------
    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        metadata = _metadata(request)
        payload = self._descriptor_payload(request, metadata)
        if request.params.get("live_validate"):
            return await self._validated_response(request, metadata, payload)
        return self._response(request, metadata, payload)

    # -------------------------------------------------------------------------
    def _descriptor_payload(
        self, request: ProviderRequest, metadata: dict[str, Any]
    ) -> dict[str, Any]:
        protocol = _protocol(metadata)
        layer_id = str(
            metadata.get("layer_id")
            or metadata.get("layers")
            or request.capability_id
        )
        base_payload: dict[str, Any] = {
            "serviceUrl": metadata.get("url"),
            "layerId": layer_id,
            "legend": {
                "title": metadata.get("label") or "ESA WorldCover",
                "source": "ESA WorldCover / Terrascope",
            },
            "freshnessLabel": "WorldCover 2021 static source layer",
        }
        if protocol == "wms":
            return {
                **base_payload,
                "renderingMode": "wms",
                "layers": layer_id,
                "crs": metadata.get("crs") or "EPSG:3857",
                "format": metadata.get("wms_format")
                or metadata.get("format")
                or "image/png",
                "style": metadata.get("style") or "",
                "version": metadata.get("wms_version") or "1.3.0",
                "exceptions": metadata.get("wms_exceptions")
                or "application/vnd.ogc.se_inimage",
            }
        return {
            **base_payload,
            "renderingMode": "wmts",
            "tileMatrixSet": metadata.get("tile_matrix_set") or "EPSG:3857",
            "format": metadata.get("wmts_format") or "image/png",
            "style": metadata.get("wmts_style") or "",
        }

    # -------------------------------------------------------------------------
    async def _validated_response(
        self,
        request: ProviderRequest,
        metadata: dict[str, Any],
        payload: dict[str, Any],
    ) -> ProviderResponse:
        protocol = _protocol(metadata).upper()
        service_url = str(payload.get("serviceUrl") or "").strip()
        cache_key = f"{self.provider_id}:{request.capability_id}:{service_url}"
        cached = self.cache.get(cache_key)
        if cached.status == CacheLookupStatus.HIT and is_json_object(cached.value):
            return self._response(
                request, metadata, {**payload, "liveValidation": cached.value}
            )
        try:
            validation = await call_json_fetcher(self.fetcher, service_url, None)
        except Exception as exc:
            if cached.status == CacheLookupStatus.STALE and is_json_object(
                cached.value
            ):
                return self._response(
                    request,
                    metadata,
                    {**payload, "liveValidation": cached.value},
                    stale=True,
                    warnings=[
                        f"ESA {protocol} validation failed; using stale validation metadata."
                    ],
                )
            if isinstance(exc, ProviderUnavailableError):
                raise
            raise ProviderUnavailableError(f"ESA {protocol} validation failed.") from exc
        if not is_json_object(validation):
            if cached.status == CacheLookupStatus.STALE and is_json_object(
                cached.value
            ):
                return self._response(
                    request,
                    metadata,
                    {**payload, "liveValidation": cached.value},
                    stale=True,
                    warnings=[
                        f"ESA {protocol} validation was malformed; using stale validation metadata."
                    ],
                )
            raise ProviderUnavailableError(
                f"ESA {protocol} validation returned malformed metadata."
            )
        self.cache.set(
            cache_key,
            validation,
            ttl_seconds=self.cache_ttl_seconds,
            stale_while_revalidate_seconds=self.stale_while_revalidate_seconds,
        )
        return self._response(
            request, metadata, {**payload, "liveValidation": validation}
        )

    # -------------------------------------------------------------------------
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
            result_type="raster",
            attribution=[str(metadata.get("attribution") or "ESA WorldCover")],
            warnings=warnings or [],
            stale=stale,
        )

###############################################################################
def _metadata(request: ProviderRequest) -> dict[str, Any]:
    value = request.params.get("metadata")
    return dict(value) if is_json_object(value) else {}


def _protocol(metadata: dict[str, Any]) -> str:
    value = str(
        metadata.get("source_protocol")
        or metadata.get("renderingMode")
        or metadata.get("rendering_mode")
        or metadata.get("type")
        or ""
    ).strip().lower()
    return "wms" if value == "wms" else "wmts"
