from __future__ import annotations

from server.common.typing import is_json_object, json_array, json_object

from datetime import UTC, datetime, timedelta
import math
from typing import Any, Literal, cast

from server.configurations.settings import OpenMeteoSettings
from server.services.geospatial.openmeteo import OpenMeteoService, OpenMeteoServiceError
from server.services.geospatial.providers._request import request_center, grid_points
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
    def __init__(
        self,
        *,
        service: OpenMeteoService | None = None,
        settings: OpenMeteoSettings | None = None,
    ) -> None:
        self.service = service or OpenMeteoService(settings=settings)

    # -------------------------------------------------------------------------
    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        if request.params.get("sampling") == "area" and request.bbox is not None and request.capability_id == "openmeteo_weather_forecast":
            return await self._weather_grid(request)
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

    async def _weather_grid(self, request: ProviderRequest) -> ProviderResponse:
        assert request.bbox is not None
        points, spacing = grid_points(request.bbox)
        now = datetime.now(UTC)
        past_days = min(14, max(0, math.ceil(max(0.0, (now - request.time).total_seconds() - 60) / 86400))) if request.time else 0
        try:
            locations = await self.service.get_weather_grid(points, past_days)
        except (OpenMeteoServiceError, ValueError) as exc:
            raise ProviderUnavailableError(str(exc)) from exc
        features: list[dict[str, Any]] = []
        excluded = 0
        partial = len(locations) != len(points)
        windows: list[tuple[str, str]] = []
        for index, payload in enumerate(locations[:len(points)]):
            if payload.get("elevation") == 0:
                excluded += 1
                continue
            current = json_object(payload.get("current"))
            hourly = json_object(payload.get("hourly"))
            current_time = current.get("time")
            times = hourly.get("time", [])
            temperatures = hourly.get("temperature_2m", [])
            precipitation = hourly.get("precipitation", [])
            if not isinstance(current_time, str):
                partial = True
                continue
            # Open-Meteo times share each point's local timezone. Compare local
            # instants only within that point and disclose the per-point window.
            local_end = datetime.fromisoformat(current_time)
            local_start = local_end - timedelta(days=past_days) if past_days else local_end.replace(hour=0, minute=0, second=0)
            selected = [i for i, stamp in enumerate(times) if isinstance(stamp, str)
                        and local_start <= datetime.fromisoformat(stamp) <= local_end]
            rain = [precipitation[i] if i < len(precipitation) else None for i in selected]
            heat = [temperatures[i] if i < len(temperatures) else None for i in selected]
            def numeric(value: Any) -> bool:
                return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
            if not selected or not all(numeric(value) for value in [*rain, *heat, current.get("temperature_2m")]):
                partial = True
                continue
            latitude, longitude = points[index]
            start, end = times[selected[0]], times[selected[-1]]
            windows.append((start, end))
            features.append({
                "id": f"openmeteo:grid:{index}", "latitude": latitude, "longitude": longitude,
                "name": f"{latitude:.5f}, {longitude:.5f}", "label_kind": "coordinates",
                "precipitation_sum_mm": sum(float(value) for value in rain if value is not None), "temperature_2m_max_c": max(float(value) for value in heat if value is not None),
                "temperature_2m_current_c": current["temperature_2m"], "elevation": payload.get("elevation"),
                "window_start": start, "window_end": end, "timezone": payload.get("timezone"),
                "value_kind": "model_estimate",
            })
        units = {"precipitation_sum_mm": "mm", "temperature_2m_max_c": "\u00b0C", "temperature_2m_current_c": "\u00b0C", "elevation": "m"}
        coverage: dict[str, Any] = {"type": "grid_sample", "bbox": list(request.bbox), "point_count": len(features),
                    "requested_point_count": len(points), "spacing_deg": spacing, "excluded_sea_points": excluded,
                    "temporal_scope_satisfied": request.time is None or now - request.time <= timedelta(days=14),
                    "missing_point_count": len(points) - excluded - len(features),
                    "window_start": min((w[0] for w in windows), default=None),
                    "window_end": max((w[1] for w in windows), default=None),
                    "value_kind": "model_estimate", "location_labels": "coordinates_only"}
        return ProviderResponse(
            capability_id=request.capability_id, provider_id=self.provider_id,
            payload={"features": features, "renderingMode": "circles", "value_kind": "model_estimate", "units": units, "coverage": coverage},
            attribution=["Open-Meteo"], coverage=coverage, units=units,
            result_type="features", result_status="valid_empty" if not features else "partial" if partial else "ok",
            partial=partial and bool(features), source_url=self.service.weather_base_url,
            observation_time=coverage["window_end"], spatial_resolution=f"{spacing:.2f} degree grid",
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
            "hourlyForecast": json_array(payload.get("hourly_forecast")),
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
