from __future__ import annotations

from server.common.typing import is_json_object, json_array, json_object

from datetime import UTC, datetime
from typing import Any, Literal, cast

from server.services.geospatial.openmeteo import OpenMeteoService, OpenMeteoServiceError
from server.services.geospatial.providers._request import request_center
from server.services.geospatial.providers.base import (
    GeospatialProvider,
    ProviderRequest,
    ProviderResponse,
    ProviderUnavailableError,
    safe_request_params,
)

ResultStatus = Literal["ok", "valid_empty", "partial", "stale"]


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
            if "elevation" in request.capability_id:
                payload = await self.service.get_elevation(
                    latitude=latitude,
                    longitude=longitude,
                )
            elif "air_quality" in request.capability_id:
                payload = await self.service.get_air_quality_forecast(
                    latitude=latitude,
                    longitude=longitude,
                )
            else:
                payload = await self.service.get_weather_forecast(
                    latitude=latitude,
                    longitude=longitude,
                )
        except (OpenMeteoServiceError, ValueError) as exc:
            raise ProviderUnavailableError(str(exc)) from exc
        payload = dict(payload)
        if not json_object(payload.get("request_parameters")):
            payload["request_parameters"] = safe_request_params(request.params)
        rendering_mode = "clustered-points"
        normalized = self._payload(payload, rendering_mode=rendering_mode)
        partial = bool(payload.get("partial"))
        raw_result_status = str(payload.get("result_status") or "").strip()
        if raw_result_status in {"ok", "valid_empty", "partial", "stale"}:
            result_status = cast(ResultStatus, raw_result_status)
        else:
            result_status = "partial" if partial else "ok"
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload=normalized,
            attribution=[str(payload.get("attribution") or "Data from Open-Meteo")],
            fetched_at=self._fetched_at(payload.get("fetched_at")),
            result_status=result_status,
            observation_time=(
                str(payload.get("observation_time"))
                if payload.get("observation_time") is not None
                else None
            ),
            coverage=json_object(payload.get("coverage")) or None,
            spatial_resolution=(
                str(payload.get("spatial_resolution"))
                if payload.get("spatial_resolution")
                else None
            ),
            units={
                str(key): str(value)
                for key, value in json_object(payload.get("units")).items()
                if isinstance(value, str)
            },
            source_url=(
                str(payload.get("source_url"))
                if payload.get("source_url") is not None
                else self._service_source_url(request.capability_id)
            ),
            result_type="features",
            partial=partial,
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
            "elevation": payload.get("elevation"),
            "timezone": payload.get("timezone"),
            "current": json_object(payload.get("current")),
            "hourlyPreview": json_array(payload.get("hourly_preview")),
            "features": self._features(payload, rendering_mode=rendering_mode),
            "resolvedAt": payload.get("resolved_at"),
            "observation_time": payload.get("observation_time"),
            "units": payload.get("units") or {},
            "spatial_resolution": payload.get("spatial_resolution"),
            "coverage": payload.get("coverage"),
            "source_url": payload.get("source_url"),
            "fetched_at": payload.get("fetched_at"),
            "result_status": payload.get("result_status"),
            "partial": bool(payload.get("partial")),
            "requested_variables": payload.get("requested_variables") or [],
            "request_parameters": payload.get("request_parameters") or {},
        }

    # -------------------------------------------------------------------------
    def _features(
        self, payload: dict[str, Any], *, rendering_mode: str
    ) -> list[dict[str, Any]]:
        if rendering_mode != "clustered-points":
            return []
        if str(payload.get("result_status") or "ok") == "valid_empty":
            return []
        latitude = payload.get("latitude")
        longitude = payload.get("longitude")
        if not isinstance(latitude, (int, float)) or not isinstance(
            longitude, (int, float)
        ):
            return []
        kind = str(payload.get("kind") or "")
        current = json_object(payload.get("current"))
        preview = json_array(payload.get("hourly_preview"))
        first_hour = preview[0] if preview and is_json_object(preview[0]) else {}
        source_url = payload.get("source_url")
        fetched_at = payload.get("fetched_at")
        result_status = payload.get("result_status")
        partial = bool(payload.get("partial"))
        common = {
            "latitude": float(latitude),
            "longitude": float(longitude),
            "source_url": source_url,
            "fetched_at": fetched_at,
            "observation_time": payload.get("observation_time"),
            "forecast_time": first_hour.get("time"),
            "timezone": payload.get("timezone"),
            "result_status": result_status,
            "partial": partial,
            "units": json_object(payload.get("units")),
            "request_parameters": json_object(payload.get("request_parameters")),
        }
        if "elevation" in kind:
            elevation = payload.get("elevation")
            return [
                {
                    "id": f"openmeteo:elevation:{latitude:.4f}:{longitude:.4f}",
                    "name": "Open-Meteo terrain elevation",
                    "category": "terrain",
                    "source": self.provider_id,
                    "latitude": float(latitude),
                    "longitude": float(longitude),
                    "elevation": elevation,
                    "metadata": {
                        "elevation": elevation,
                        "spatial_resolution": payload.get("spatial_resolution"),
                        **common,
                    },
                }
            ]
        if "air_quality" in kind:
            pollutant_values = {
                key: self._prefer(current.get(key), first_hour.get(key))
                for key in (
                    "pm2_5",
                    "pm10",
                    "nitrogen_dioxide",
                    "ozone",
                    "sulphur_dioxide",
                    "carbon_monoxide",
                )
            }
            return [
                {
                    "id": f"openmeteo:air-quality:{latitude:.4f}:{longitude:.4f}",
                    "name": "Open-Meteo air quality forecast",
                    "category": "air_quality",
                    "source": self.provider_id,
                    "latitude": float(latitude),
                    "longitude": float(longitude),
                    **pollutant_values,
                    "metadata": {
                        "pollutantSymbols": {
                            "pm25": pollutant_values["pm2_5"],
                            "pm10": pollutant_values["pm10"],
                            "no2": pollutant_values["nitrogen_dioxide"],
                            "o3": pollutant_values["ozone"],
                            "so2": pollutant_values["sulphur_dioxide"],
                            "co": pollutant_values["carbon_monoxide"],
                        },
                        **common,
                    },
                }
            ]
        weather_values = {
            key: self._prefer(current.get(key), first_hour.get(key))
            for key in (
                "temperature_2m",
                "precipitation",
                "weather_code",
                "relative_humidity_2m",
                "surface_pressure",
                "wind_speed_10m",
                "wind_direction_10m",
                "wind_gusts_10m",
                "precipitation_probability",
            )
        }
        return [
            {
                "id": f"openmeteo:wind:{latitude:.4f}:{longitude:.4f}",
                "name": "Open-Meteo wind forecast",
                "category": "wind",
                "source": self.provider_id,
                "latitude": float(latitude),
                "longitude": float(longitude),
                **weather_values,
                "metadata": {
                    "windArrow": {
                        "speed": weather_values["wind_speed_10m"],
                        "direction": weather_values["wind_direction_10m"],
                    },
                    "pressure": weather_values["surface_pressure"],
                    "humidity": weather_values["relative_humidity_2m"],
                    **common,
                },
            }
        ]

    # -------------------------------------------------------------------------
    def _service_source_url(self, capability_id: str) -> str | None:
        if "elevation" in capability_id:
            return getattr(self.service, "elevation_base_url", None)
        if "air_quality" in capability_id:
            return getattr(self.service, "air_quality_base_url", None)
        return getattr(self.service, "weather_base_url", None)

    # -------------------------------------------------------------------------
    @staticmethod
    def _prefer(primary: object, fallback: object) -> object:
        return primary if primary is not None else fallback

    # -------------------------------------------------------------------------
    @staticmethod
    def _fetched_at(value: object) -> datetime:
        if isinstance(value, datetime):
            return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        if isinstance(value, str) and value.strip():
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                parsed = None
            if parsed is not None:
                return (
                    parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
                )
        return datetime.now(UTC)
