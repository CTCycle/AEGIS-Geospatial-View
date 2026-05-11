from __future__ import annotations

from typing import Any

from server.services.geospatial.openaq import OpenAQService, OpenAQServiceError
from server.services.geospatial.providers._request import request_center, request_radius_m
from server.services.geospatial.providers.base import (
    GeospatialProvider,
    ProviderRequest,
    ProviderResponse,
    ProviderUnavailableError,
)


class OpenAQProvider(GeospatialProvider):
    provider_id = "openaq"

    def __init__(self, *, service: OpenAQService | None = None) -> None:
        self.service = service or OpenAQService()

    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        latitude, longitude = request_center(request)
        radius_m = request_radius_m(request, self.service.default_radius_m)
        try:
            payload = await self.service.get_nearby_measurements(
                lat=latitude,
                lon=longitude,
                radius_m=radius_m,
            )
        except (OpenAQServiceError, ValueError) as exc:
            raise ProviderUnavailableError(str(exc)) from exc
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={
                "renderingMode": "clustered-points",
                "features": self._features(payload),
                "summary": payload.get("summary") or {},
                "center": payload.get("center")
                or {"latitude": latitude, "longitude": longitude},
                "radiusM": radius_m,
            },
            attribution=[str(payload.get("attribution") or "Data from OpenAQ")],
        )

    def _features(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        features = []
        for location in payload.get("locations") or []:
            if not isinstance(location, dict):
                continue
            features.append(
                {
                    "id": str(location.get("id") or ""),
                    "name": location.get("name"),
                    "latitude": location.get("latitude"),
                    "longitude": location.get("longitude"),
                    "measurements": location.get("measurements") or {},
                    "distanceM": location.get("distance_m"),
                    "metadata": {
                        "country": location.get("country"),
                        "city": location.get("city"),
                    },
                }
            )
        return features
