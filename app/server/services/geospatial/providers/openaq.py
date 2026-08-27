from __future__ import annotations

from server.common.typing import is_json_array, is_json_object, json_array, json_object

from typing import Any

from server.services.geospatial.cache import CacheLookupStatus, GeospatialCache
from server.services.geospatial.openaq import (
    OpenAQAuthError,
    OpenAQInvalidQueryError,
    OpenAQMalformedPayloadError,
    OpenAQRateLimitError,
    OpenAQService,
    OpenAQServiceError,
)
from server.services.geospatial.providers._request import (
    request_center,
    request_radius_m,
)
from server.services.geospatial.providers.base import (
    GeospatialProvider,
    ProviderAuthError,
    ProviderInvalidQueryError,
    ProviderMalformedPayloadError,
    ProviderRateLimitError,
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
        if cached.status == CacheLookupStatus.HIT and is_json_object(cached.value):
            return self._response(request, cached.value, stale=False)
        try:
            payload = await self.service.get_nearby_measurements(
                lat=latitude,
                lon=longitude,
                radius_m=radius_m,
            )
        except OpenAQAuthError as exc:
            raise ProviderAuthError("OpenAQ rejected the configured API key.") from exc
        except OpenAQInvalidQueryError as exc:
            raise ProviderInvalidQueryError("OpenAQ rejected the requested query.") from exc
        except OpenAQRateLimitError as exc:
            if cached.status == CacheLookupStatus.STALE and is_json_object(cached.value):
                return self._response(
                    request,
                    cached.value,
                    stale=True,
                    warnings=["OpenAQ rate limit reached; using stale cached station data."],
                )
            raise ProviderRateLimitError("OpenAQ rate limit exceeded.") from exc
        except OpenAQMalformedPayloadError as exc:
            if cached.status == CacheLookupStatus.STALE and is_json_object(cached.value):
                return self._response(
                    request,
                    cached.value,
                    stale=True,
                    warnings=["OpenAQ returned malformed data; using stale cached station data."],
                )
            raise ProviderMalformedPayloadError("OpenAQ returned malformed data.") from exc
        except (OpenAQServiceError, ValueError) as exc:
            if cached.status == CacheLookupStatus.STALE and is_json_object(cached.value):
                return self._response(
                    request,
                    cached.value,
                    stale=True,
                    warnings=[
                        "OpenAQ measurement refresh failed; using stale cached station data."
                    ],
                )
            raise ProviderUnavailableError(str(exc)) from exc
        if not is_json_object(payload) or not is_json_array(payload.get("locations")):
            raise ProviderMalformedPayloadError(
                "OpenAQ service returned a payload without locations."
            )
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
            result_status="stale"
            if stale
            else "valid_empty"
            if public_payload.get("features") == []
            else "ok",
            result_type="features",
        )

    # -------------------------------------------------------------------------
    def _features(
        self, payload: dict[str, Any], *, pollutants: list[str]
    ) -> list[dict[str, Any]]:
        features: list[dict[str, Any]] = []
        for location in json_array(payload.get("locations")):
            location = json_object(location)
            if not location:
                continue
            measurements = self._filter_measurements(
                json_object(location.get("measurements")), pollutants
            )
            if not measurements:
                continue
            latitude = location.get("latitude")
            longitude = location.get("longitude")
            if not isinstance(latitude, int | float) or not isinstance(
                longitude, int | float
            ):
                continue
            features.append(
                {
                    "id": str(location.get("id") or ""),
                    "name": location.get("name"),
                    "latitude": float(latitude),
                    "longitude": float(longitude),
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
        elif is_json_array(raw):
            values = [str(item).strip().lower() for item in raw]
        else:
            values = sorted(self.supported_pollutants)
        filtered = [item for item in values if item in self.supported_pollutants]
        return filtered or sorted(self.supported_pollutants)

    # -------------------------------------------------------------------------
    def _filter_measurements(
        self, measurements: Any, pollutants: list[str]
    ) -> dict[str, Any]:
        if not is_json_object(measurements):
            return {}
        allowed = set(pollutants)
        return {
            key: value
            for key, value in measurements.items()
            if str(key).lower() in allowed
        }
