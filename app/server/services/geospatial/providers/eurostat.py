from __future__ import annotations

from typing import Any

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


class EurostatProvider(GeospatialProvider):
    provider_id = "eurostat"

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
        elif request.params.get("joined_features"):
            payload = _build_choropleth_payload(request, metadata)
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
        if request.params.get("live_validate") and payload.get("datasetUrl"):
            return await self._validated_response(request, metadata, payload)
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload=payload,
            attribution=[str(metadata.get("attribution") or "Eurostat")],
        )

    async def _validated_response(
        self,
        request: ProviderRequest,
        metadata: dict[str, Any],
        payload: dict[str, Any],
    ) -> ProviderResponse:
        dataset_url = str(payload.get("datasetUrl") or "").strip()
        cache_key = f"{self.provider_id}:{request.capability_id}:{dataset_url}"
        cached = self.cache.get(cache_key)
        if cached.status == CacheLookupStatus.HIT and isinstance(cached.value, dict):
            return _response(request, metadata, {**payload, "jsonStatMetadata": cached.value})
        try:
            metadata_payload = await call_json_fetcher(self.fetcher, dataset_url, None)
        except Exception as exc:
            if cached.status == CacheLookupStatus.STALE and isinstance(cached.value, dict):
                return _response(
                    request,
                    metadata,
                    {**payload, "jsonStatMetadata": cached.value},
                    stale=True,
                    warnings=["Eurostat JSON-stat metadata refresh failed; using stale metadata."],
                )
            if isinstance(exc, ProviderUnavailableError):
                raise
            raise ProviderUnavailableError("Eurostat JSON-stat metadata fetch failed.") from exc
        normalized = _normalize_jsonstat_metadata(metadata_payload)
        if normalized is None:
            if cached.status == CacheLookupStatus.STALE and isinstance(cached.value, dict):
                return _response(
                    request,
                    metadata,
                    {**payload, "jsonStatMetadata": cached.value},
                    stale=True,
                    warnings=["Eurostat JSON-stat metadata was malformed; using stale metadata."],
                )
            raise ProviderUnavailableError("Eurostat JSON-stat metadata was malformed.")
        self.cache.set(
            cache_key,
            normalized,
            ttl_seconds=self.cache_ttl_seconds,
            stale_while_revalidate_seconds=self.stale_while_revalidate_seconds,
        )
        return _response(request, metadata, {**payload, "jsonStatMetadata": normalized})


def _metadata(request: ProviderRequest) -> dict[str, Any]:
    value = request.params.get("metadata")
    return dict(value) if isinstance(value, dict) else {}


def _response(
    request: ProviderRequest,
    metadata: dict[str, Any],
    payload: dict[str, Any],
    *,
    stale: bool = False,
    warnings: list[str] | None = None,
) -> ProviderResponse:
    return ProviderResponse(
        capability_id=request.capability_id,
        provider_id=EurostatProvider.provider_id,
        payload=payload,
        attribution=[str(metadata.get("attribution") or "Eurostat")],
        warnings=warnings or [],
        stale=stale,
    )


def _normalize_jsonstat_metadata(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    dimensions = value.get("dimension")
    ids = value.get("id")
    size = value.get("size")
    if not isinstance(dimensions, dict) or not isinstance(ids, list):
        return None
    return {
        "id": [str(item) for item in ids],
        "size": size if isinstance(size, list) else [],
        "dimensions": sorted(str(key) for key in dimensions),
        "label": value.get("label"),
        "updated": value.get("updated"),
    }


def _build_choropleth_payload(
    request: ProviderRequest, metadata: dict[str, Any]
) -> dict[str, Any]:
    joined = request.params.get("joined_features")
    features = list(joined) if isinstance(joined, list) else []
    metric = str(request.params.get("metric") or metadata.get("label") or "value")
    values = [
        float(feature.get("properties", {}).get("value"))
        for feature in features
        if isinstance(feature, dict)
        and isinstance(feature.get("properties"), dict)
        and isinstance(feature["properties"].get("value"), int | float)
    ]
    bins = _legend_bins(values)
    enriched_features = []
    for feature in features:
        if not isinstance(feature, dict):
            continue
        properties = dict(feature.get("properties") or {})
        properties.setdefault("metric", metric)
        properties.setdefault("vintage", request.params.get("vintage") or metadata.get("vintage"))
        properties.setdefault("source", "Eurostat")
        if request.params.get("margin_of_error") is not None:
            properties.setdefault("marginOfError", request.params["margin_of_error"])
        enriched_features.append({**feature, "properties": properties})
    return {
        "renderingMode": "choropleth",
        "status": "joined",
        "metric": metric,
        "vintage": request.params.get("vintage") or metadata.get("vintage"),
        "marginOfError": request.params.get("margin_of_error"),
        "source": "Eurostat",
        "joinKey": "NUTS_ID",
        "legendBins": bins,
        "featureCollection": {"type": "FeatureCollection", "features": enriched_features},
    }


def _legend_bins(values: list[float]) -> list[dict[str, float]]:
    if not values:
        return []
    low = min(values)
    high = max(values)
    if low == high:
        return [{"min": low, "max": high}]
    step = (high - low) / 4
    return [
        {"min": low + step * index, "max": low + step * (index + 1)}
        for index in range(4)
    ]
