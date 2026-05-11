from __future__ import annotations

from typing import Any

from server.services.geospatial.openmeteo import OpenMeteoService, OpenMeteoServiceError
from server.services.geospatial.providers._request import request_center
from server.services.geospatial.providers.base import (
    GeospatialProvider,
    ProviderRequest,
    ProviderResponse,
    ProviderUnavailableError,
)


class OpenMeteoProvider(GeospatialProvider):
    provider_id = "openmeteo"

    def __init__(self, *, service: OpenMeteoService | None = None) -> None:
        self.service = service or OpenMeteoService()

    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        latitude, longitude = request_center(request)
        try:
            if "air_quality" in request.capability_id:
                payload = await self.service.get_air_quality_forecast(
                    latitude=latitude,
                    longitude=longitude,
                )
                rendering_mode = "clustered-points"
            else:
                payload = await self.service.get_weather_forecast(
                    latitude=latitude,
                    longitude=longitude,
                )
                rendering_mode = (
                    "clustered-points"
                    if "pressure_humidity_wind" in request.capability_id
                    else "metadata-only"
                )
        except (OpenMeteoServiceError, ValueError) as exc:
            raise ProviderUnavailableError(str(exc)) from exc
        normalized = self._payload(payload, rendering_mode=rendering_mode)
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload=normalized,
            attribution=[str(payload.get("attribution") or "Data from Open-Meteo")],
        )

    def _payload(
        self, payload: dict[str, Any], *, rendering_mode: str
    ) -> dict[str, Any]:
        return {
            "renderingMode": rendering_mode,
            "provider": self.provider_id,
            "kind": payload.get("kind"),
            "latitude": payload.get("latitude"),
            "longitude": payload.get("longitude"),
            "timezone": payload.get("timezone"),
            "current": payload.get("current") or {},
            "hourlyPreview": payload.get("hourly_preview") or [],
            "resolvedAt": payload.get("resolved_at"),
        }
