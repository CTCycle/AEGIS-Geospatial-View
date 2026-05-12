from __future__ import annotations

from typing import Any

from server.services.geospatial.providers.base import (
    GeospatialProvider,
    ProviderRequest,
    ProviderResponse,
)


class ESAProvider(GeospatialProvider):
    provider_id = "esa"

    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        metadata = _metadata(request)
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={
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
            },
            attribution=[str(metadata.get("attribution") or "ESA WorldCover")],
        )


def _metadata(request: ProviderRequest) -> dict[str, Any]:
    value = request.params.get("metadata")
    return dict(value) if isinstance(value, dict) else {}
