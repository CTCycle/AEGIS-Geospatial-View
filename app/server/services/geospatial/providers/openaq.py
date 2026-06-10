from __future__ import annotations

from typing import Any

from server.services.geospatial.cache import CacheLookupStatus, GeospatialCache
from server.services.geospatial.openaq import OpenAQService, OpenAQServiceError
from server.services.geospatial.providers._request import (
    request_center,
    request_radius_m,
)
from server.services.geospatial.providers.base import (
    GeospatialProvider,
    ProviderAuthError,
    ProviderRequest,
    ProviderResponse,
    ProviderUnavailableError,
)


###############################################################################
class OpenAQProvider(GeospatialProvider):
    provider_id = "openaq"
    supported_pollutants = {"pm25", "pm10", "no2", "o3", "so2", "co"}

    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        api_key: str | None = None,
        service: OpenAQService | None = None,
        cache: GeospatialCache | None = None,
        cache_ttl_seconds: int = 300,
        stale_while_revalidate_seconds: int = 3600,
    ) -> None:
        self.api_key = (api_key or "").strip()
        self.service = service or OpenAQService(api_key=self.api_key)
        self.cache = cache or GeospatialCache()
        self.cache_ttl_seconds = cache_ttl_seconds
        self.stale_while_revalidate_seconds = stale_while_revalidate_seconds

    # -------------------------------------------------------------------------
    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        if not self.api_key:
            raise ProviderAuthError("OpenAQ API key is required.")
        latitude, longitude = request_center(request)
        radius_m = request_radius_m(request, self.service.default_radius_m)
        pollutants = self._pollutants(request)
        cache_key = (
            f"openaq:{latitude:.4f}:{longitude:.4f}:{radius_m:.0f}:"
            f"{','.join(pollutants)}"
        )
        cached = self.cache.get(cache_key)
        if cached.status == CacheLookupStatus.HIT and isinstance(cached.value, dict):
            return self._response(request, cached.value, stale=False)
        try:
            payload = await self.service.get_nearby_measurements(
                lat=latitude,
                lon=longitude,
                radius_m=radius_m,
            )
        except (OpenAQServiceError, ValueError) as exc:
            if cached.status == CacheLookupStatus.STALE and isinstance(cached.value, dict):
                return self._response(
                    request,
                    cached.value,
                    stale=True,
                    warnings=[
                        "OpenAQ measurement refresh failed; using stale cached station data."
                    ],
                )
            raise ProviderUnavailableError(str(exc)) from exc
        normalized = {
            "renderingMode": "clustered-points",
            "features": self._features(payload, pollutants=pollutants),
            "summary": self._filter_measurements(payload.get("summary") or {}, pollutants),
            "center": payload.get("center")
            or {"latitude": latitude, "longitude": longitude},
            "radiusM": radius_m,
            "pollutants": pollutants,
            "attribution": str(payload.get("attribution") or "Data from OpenAQ"),
        }
        self.cache.set(
            cache_key,
            normalized,
            ttl_seconds=self.cache_ttl_seconds,
            stale_while_revalidate_seconds=self.stale_while_revalidate_seconds,
        )
        return self._response(request, normalized, stale=False)

    # -------------------------------------------------------------------------
    def _response(
        self,
        request: ProviderRequest,
        payload: dict[str, Any],
        *,
        stale: bool,
        warnings: list[str] | None = None,
    ) -> ProviderResponse:
        attribution = str(payload.get("attribution") or "Data from OpenAQ")
        public_payload = dict(payload)
        public_payload.pop("attribution", None)
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload=public_payload,
            attribution=[attribution],
            warnings=warnings or [],
            stale=stale,
        )

    # -------------------------------------------------------------------------
    def _features(
        self, payload: dict[str, Any], *, pollutants: list[str]
    ) -> list[dict[str, Any]]:
        features = []
        for location in payload.get("locations") or []:
            if not isinstance(location, dict):
                continue
            measurements = self._filter_measurements(
                location.get("measurements") or {}, pollutants
            )
            if not measurements:
                continue
            features.append(
                {
                    "id": str(location.get("id") or ""),
                    "name": location.get("name"),
                    "latitude": location.get("latitude"),
                    "longitude": location.get("longitude"),
                    "measurements": measurements,
                    "distanceM": location.get("distance_m"),
                    "metadata": {
                        "country": location.get("country"),
                        "city": location.get("city"),
                    },
                }
            )
        return features

    # -------------------------------------------------------------------------
    def _pollutants(self, request: ProviderRequest) -> list[str]:
        raw = request.params.get("pollutants") or request.params.get("pollutant")
        if isinstance(raw, str):
            values = [item.strip().lower() for item in raw.split(",")]
        elif isinstance(raw, list):
            values = [str(item).strip().lower() for item in raw]
        else:
            values = sorted(self.supported_pollutants)
        filtered = [item for item in values if item in self.supported_pollutants]
        return filtered or sorted(self.supported_pollutants)

    # -------------------------------------------------------------------------
    def _filter_measurements(
        self, measurements: Any, pollutants: list[str]
    ) -> dict[str, Any]:
        if not isinstance(measurements, dict):
            return {}
        allowed = set(pollutants)
        return {
            key: value
            for key, value in measurements.items()
            if str(key).lower() in allowed
        }
