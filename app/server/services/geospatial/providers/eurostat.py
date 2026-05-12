from __future__ import annotations

from typing import Any

from server.services.geospatial.providers.base import (
    GeospatialProvider,
    ProviderRequest,
    ProviderResponse,
)


class EurostatProvider(GeospatialProvider):
    provider_id = "eurostat"

    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        metadata = _metadata(request)
        if request.capability_id == "eurostat_nuts_regions":
            payload = {
                "renderingMode": "vector-tile",
                "status": "dataset-ingestion",
                "sourceUrl": request.params.get("source_url") or metadata.get("url"),
                "tileManifestUrl": request.params.get("tile_manifest_url"),
                "joinKey": "NUTS_ID",
                "expectedGeometry": "Polygon",
                "freshnessLabel": "Preprocessed NUTS geometry source",
            }
        else:
            payload = {
                "renderingMode": "metadata-only",
                "status": "metadata-only",
                "datasetUrl": metadata.get("url"),
                "metric": request.params.get("metric") or metadata.get("label"),
                "source": "Eurostat",
                "joinRequired": True,
                "joinKey": "NUTS_ID",
                "message": (
                    "Eurostat statistical indicators require a materialized NUTS "
                    "geometry join before choropleth rendering."
                ),
            }
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload=payload,
            attribution=[str(metadata.get("attribution") or "Eurostat")],
        )


def _metadata(request: ProviderRequest) -> dict[str, Any]:
    value = request.params.get("metadata")
    return dict(value) if isinstance(value, dict) else {}
