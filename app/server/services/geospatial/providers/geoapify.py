from __future__ import annotations

from urllib.parse import urlencode
from collections.abc import Mapping

from server.domain.geographics import ProviderCredentialValidationResult
from server.services.geospatial.cache import CacheLookupStatus, GeospatialCache
from server.services.geospatial.normalizers import (
    NormalizationError,
    normalize_poi_category,
    normalize_poi_feature,
)
from server.services.geospatial.providers.base import (
    GeospatialProvider,
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


class GeoapifyProvider(GeospatialProvider):
    provider_id = "geoapify"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        fetcher: JsonFetcher | None = None,
        cache: GeospatialCache | None = None,
        cache_ttl_seconds: int = 3600,
        stale_while_revalidate_seconds: int = 86400,
    ) -> None:
        self.api_key = (api_key or "").strip()
        self.fetcher = fetcher or fetch_json_url
        self.cache = cache or GeospatialCache()
        self.cache_ttl_seconds = cache_ttl_seconds
        self.stale_while_revalidate_seconds = stale_while_revalidate_seconds

    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        if not self.api_key:
            raise ProviderAuthError("Geoapify API key is required.")
        if "osm" in request.capability_id:
            return ProviderResponse(
                capability_id=request.capability_id,
                provider_id=self.provider_id,
                payload={
                    "renderingMode": "raster-tile",
                    "tileUrl": (
                        "https://maps.geoapify.com/v1/tile/osm-bright/"
                        f"{{z}}/{{x}}/{{y}}.png?apiKey={self.api_key}"
                    ),
                    "credentialPolicy": "server-side-or-existing-browser-key-only",
                },
                attribution=["Geoapify, OpenStreetMap contributors"],
            )
        if request.params.get("live"):
            cache_key = _cache_key(request)
            cached = self.cache.get(cache_key)
            if cached.status == CacheLookupStatus.HIT and isinstance(cached.value, dict):
                return _places_response(request, cached.value, stale=False)
            url = _build_places_url(request, self.api_key)
            payload = await call_json_fetcher(self.fetcher, url)
            features = _normalize_places_payload(payload)
            normalized_payload = {
                "renderingMode": "clustered-points",
                "features": features,
                "totalResults": len(features),
                "credentialPolicy": "server-side-only",
            }
            self.cache.set(
                cache_key,
                normalized_payload,
                ttl_seconds=self.cache_ttl_seconds,
                stale_while_revalidate_seconds=self.stale_while_revalidate_seconds,
            )
            return _places_response(request, normalized_payload, stale=False)
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={
                "renderingMode": "clustered-points",
                "featuresEndpoint": "/api/geospatial/layers/geoapify_amenities/features",
                "credentialPolicy": "server-side-only",
            },
            attribution=["Geoapify, OpenStreetMap contributors"],
        )

    async def validate_credentials(
        self, credentials: Mapping[str, str]
    ) -> ProviderCredentialValidationResult:
        api_key = credentials.get("api_key", "").strip()
        if not api_key:
            return ProviderCredentialValidationResult(
                provider_id=self.provider_id,
                valid=False,
                status="invalid",
                message="Geoapify API key is required.",
            )
        request = ProviderRequest(
            capability_id="geoapify_amenities",
            bbox=(-0.2, 51.45, -0.1, 51.55),
            params={"live": True, "limit": 1, "categories": "amenity"},
        )
        try:
            payload = await call_json_fetcher(self.fetcher, _build_places_url(request, api_key))
            _normalize_places_payload(payload)
        except ProviderAuthError:
            return ProviderCredentialValidationResult(
                provider_id=self.provider_id,
                valid=False,
                status="invalid",
                message="Geoapify rejected the supplied API key.",
            )
        except ProviderError:
            return ProviderCredentialValidationResult(
                provider_id=self.provider_id,
                valid=False,
                status="error",
                message="Geoapify validation request failed.",
            )
        return ProviderCredentialValidationResult(
            provider_id=self.provider_id,
            valid=True,
            status="valid",
            message="Geoapify accepted the supplied API key.",
        )


def _build_places_url(request: ProviderRequest, api_key: str) -> str:
    categories = str(request.params.get("categories") or "amenity").strip()
    params = {
        "categories": categories,
        "limit": str(request.params.get("limit") or 100),
        "apiKey": api_key,
    }
    if request.bbox is not None:
        west, south, east, north = request.bbox
        params["filter"] = f"rect:{west},{north},{east},{south}"
        params["bias"] = f"rect:{west},{north},{east},{south}"
    return f"https://api.geoapify.com/v2/places?{urlencode(params)}"


def _cache_key(request: ProviderRequest) -> str:
    bbox = ",".join(str(part) for part in request.bbox or ())
    categories = str(request.params.get("categories") or "amenity").strip()
    limit = str(request.params.get("limit") or 100)
    return f"geoapify:places:{bbox}:{categories}:{limit}"


def _places_response(
    request: ProviderRequest, payload: dict[str, object], *, stale: bool
) -> ProviderResponse:
    return ProviderResponse(
        capability_id=request.capability_id,
        provider_id="geoapify",
        payload=payload,
        attribution=["Geoapify, OpenStreetMap contributors"],
        stale=stale,
    )


def _normalize_places_payload(payload: object) -> list[dict[str, object]]:
    if not isinstance(payload, dict):
        return []
    raw_features = payload.get("features")
    if not isinstance(raw_features, list):
        return []
    features: list[dict[str, object]] = []
    for item in raw_features:
        if not isinstance(item, dict):
            continue
        properties = item.get("properties") if isinstance(item.get("properties"), dict) else {}
        geometry = item.get("geometry") if isinstance(item.get("geometry"), dict) else {}
        coordinates = geometry.get("coordinates")
        if not isinstance(coordinates, list) or len(coordinates) < 2:
            continue
        raw_category = _first_category(properties.get("categories"))
        normalized = {
            "id": properties.get("place_id") or properties.get("id"),
            "name": properties.get("name"),
            "latitude": properties.get("lat") or coordinates[1],
            "longitude": properties.get("lon") or coordinates[0],
            "address": properties.get("formatted"),
            "website": properties.get("website"),
            "phone": properties.get("phone"),
            "category_raw": raw_category,
        }
        try:
            features.append(
                normalize_poi_feature(
                    normalized,
                    source="geoapify",
                    category=normalize_poi_category(raw_category),
                ).model_dump(mode="json")
            )
        except NormalizationError:
            continue
    return features


def _first_category(value: object) -> str:
    if isinstance(value, list) and value:
        return str(value[0])
    if isinstance(value, str):
        return value
    return "amenity"
