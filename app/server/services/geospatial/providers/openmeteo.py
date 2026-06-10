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


###############################################################################
class OpenMeteoProvider(GeospatialProvider):
    provider_id = "openmeteo"

    # -------------------------------------------------------------------------
    def __init__(self, *, service: OpenMeteoService | None = None) -> None:
        self.service = service or OpenMeteoService()

    # -------------------------------------------------------------------------
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

    # -------------------------------------------------------------------------
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
            "features": self._features(payload, rendering_mode=rendering_mode),
            "resolvedAt": payload.get("resolved_at"),
        }

    # -------------------------------------------------------------------------
    def _features(
        self, payload: dict[str, Any], *, rendering_mode: str
    ) -> list[dict[str, Any]]:
        if rendering_mode != "clustered-points":
            return []
        latitude = payload.get("latitude")
        longitude = payload.get("longitude")
        if not isinstance(latitude, (int, float)) or not isinstance(
            longitude, (int, float)
        ):
            return []
        kind = str(payload.get("kind") or "")
        current = payload.get("current") if isinstance(payload.get("current"), dict) else {}
        preview = payload.get("hourly_preview") if isinstance(payload.get("hourly_preview"), list) else []
        first_hour = preview[0] if preview and isinstance(preview[0], dict) else {}
        if "air_quality" in kind:
            return [
                {
                    "id": f"openmeteo:air-quality:{latitude:.4f}:{longitude:.4f}",
                    "name": "Open-Meteo air quality forecast",
                    "category": "air_quality",
                    "source": self.provider_id,
                    "latitude": float(latitude),
                    "longitude": float(longitude),
                    "metadata": {
                        "pollutantSymbols": {
                            "pm25": first_hour.get("pm2_5"),
                            "pm10": first_hour.get("pm10"),
                            "no2": first_hour.get("nitrogen_dioxide"),
                            "o3": first_hour.get("ozone"),
                            "so2": first_hour.get("sulphur_dioxide"),
                            "co": first_hour.get("carbon_monoxide"),
                        },
                        "forecastTime": first_hour.get("time"),
                    },
                }
            ]
        return [
            {
                "id": f"openmeteo:wind:{latitude:.4f}:{longitude:.4f}",
                "name": "Open-Meteo wind forecast",
                "category": "wind",
                "source": self.provider_id,
                "latitude": float(latitude),
                "longitude": float(longitude),
                "metadata": {
                    "windArrow": {
                        "speed": current.get("wind_speed_10m")
                        or first_hour.get("wind_speed_10m"),
                        "direction": current.get("wind_direction_10m")
                        or first_hour.get("wind_direction_10m"),
                    },
                    "pressure": current.get("surface_pressure")
                    or first_hour.get("surface_pressure"),
                    "humidity": current.get("relative_humidity_2m")
                    or first_hour.get("relative_humidity_2m"),
                    "forecastTime": first_hour.get("time"),
                },
            }
        ]
