from __future__ import annotations

from typing import Any

from server.services.geospatial.providers.base import (
    GeospatialProvider,
    ProviderRequest,
    ProviderResponse,
)


class EEAProvider(GeospatialProvider):
    provider_id = "eea"

    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        metadata = _metadata(request)
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={
                "renderingMode": "wms",
                "serviceUrl": metadata.get("url"),
                "layers": [str(metadata.get("layers") or "0")],
                "version": str(metadata.get("wms_version") or "1.1.1"),
                "exceptions": metadata.get("wms_exceptions"),
                "format": str(request.params.get("format") or "image/png"),
                "bounds": metadata.get("bounds"),
                "legend": {
                    "title": metadata.get("label") or request.capability_id,
                    "source": "European Environment Agency",
                },
                "freshnessLabel": "Static 2019 source layer",
            },
            attribution=[str(metadata.get("attribution") or "European Environment Agency")],
        )


def _metadata(request: ProviderRequest) -> dict[str, Any]:
    value = request.params.get("metadata")
    return dict(value) if isinstance(value, dict) else {}
