from __future__ import annotations

from server.common.typing import is_json_object, json_array, json_object

import asyncio
import json
import threading
import time
from datetime import UTC, datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from server.configurations import get_server_settings


###############################################################################
class OpenMeteoServiceError(Exception):
    """Base exception for Open-Meteo failures."""


###############################################################################
class OpenMeteoRequestError(OpenMeteoServiceError):
    """Raised when Open-Meteo cannot fulfill a request."""


###############################################################################
class OpenMeteoService:
    WEATHER_VARIABLES = (
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
    WEATHER_CURRENT_VARIABLES = (
        "temperature_2m",
        "precipitation",
        "weather_code",
        "relative_humidity_2m",
        "surface_pressure",
        "wind_speed_10m",
        "wind_direction_10m",
        "wind_gusts_10m",
    )
    AIR_QUALITY_VARIABLES = (
        "pm10",
        "pm2_5",
        "carbon_monoxide",
        "nitrogen_dioxide",
        "ozone",
        "sulphur_dioxide",
    )

    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        weather_base_url: str | None = None,
        air_quality_base_url: str | None = None,
        user_agent: str | None = None,
        timeout_s: float | None = None,
        cache_ttl_s: float | None = None,
        min_call_interval_s: float | None = None,
    ) -> None:
        settings = get_server_settings().openmeteo
        self.weather_base_url = weather_base_url or settings.weather_base_url
        self.air_quality_base_url = (
            air_quality_base_url or settings.air_quality_base_url
        )
        self.user_agent = user_agent or settings.user_agent
        self.timeout_s = timeout_s if timeout_s is not None else settings.timeout
        self.cache_ttl_s = max(
            cache_ttl_s if cache_ttl_s is not None else settings.cache_ttl_s, 30.0
        )
        self.min_call_interval_s = max(
            min_call_interval_s
            if min_call_interval_s is not None
            else settings.min_call_interval_s,
            0.05,
        )
        self._lock = threading.Lock()
        self._last_call_by_key: dict[str, float] = {}
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}

    # -------------------------------------------------------------------------
    async def get_weather_forecast(
        self, *, latitude: float, longitude: float
    ) -> dict[str, Any]:
        params = {
            "latitude": f"{latitude:.6f}",
            "longitude": f"{longitude:.6f}",
            "hourly": ",".join(self.WEATHER_VARIABLES),
            "current": ",".join(self.WEATHER_CURRENT_VARIABLES),
            "forecast_days": "3",
            "timezone": "auto",
        }
        payload = await asyncio.to_thread(
            self._get_json,
            endpoint=self.weather_base_url,
            params=params,
            provider_key="openmeteo_weather",
        )
        fetched_at = datetime.now(UTC).isoformat()
        hourly = json_object(payload.get("hourly"))
        timeline = list(hourly.get("time") or [])
        series = {
            name: self._series(hourly.get(name)) for name in self.WEATHER_VARIABLES
        }
        preview: list[dict[str, Any]] = []
        hourly_forecast: list[dict[str, Any]] = []
        for index in range(min(72, len(timeline))):
            row = {"time": timeline[index]}
            row.update(
                {
                    name: values[index] if index < len(values) else None
                    for name, values in series.items()
                }
            )
            hourly_forecast.append(row)
            if len(preview) >= 6:
                continue
            preview.append(row)
        current = json_object(payload.get("current"))
        partial = self._is_partial(
            timeline=timeline,
            series=series,
            current=current,
            current_variables=self.WEATHER_CURRENT_VARIABLES,
        )
        result_status = self._result_status(
            timeline=timeline,
            current=current,
            variables=self.WEATHER_CURRENT_VARIABLES,
            partial=partial,
        )
        return {
            "provider": "openmeteo",
            "kind": "weather_forecast",
            "source_url": self.weather_base_url,
            "fetched_at": fetched_at,
            "result_status": result_status,
            "result_type": "metadata",
            "partial": partial,
            "latitude": latitude,
            "longitude": longitude,
            "timezone": payload.get("timezone"),
            "current": current,
            "hourly_preview": preview,
            "hourly_forecast": hourly_forecast,
            "resolved_at": fetched_at,
            "observation_time": current.get("time"),
            "units": self._units(payload),
            "requested_variables": list(self.WEATHER_VARIABLES),
            "request_parameters": dict(params),
            "spatial_resolution": "point forecast",
            "coverage": {
                "type": "point",
                "latitude": latitude,
                "longitude": longitude,
            },
            "attribution": "Data from Open-Meteo",
        }

    # -------------------------------------------------------------------------
    async def get_air_quality_forecast(
        self, *, latitude: float, longitude: float
    ) -> dict[str, Any]:
        params = {
            "latitude": f"{latitude:.6f}",
            "longitude": f"{longitude:.6f}",
            "hourly": "pm10,pm2_5,carbon_monoxide,nitrogen_dioxide,ozone,sulphur_dioxide",
            "timezone": "auto",
            "forecast_days": "3",
        }
        payload = await asyncio.to_thread(
            self._get_json,
            endpoint=self.air_quality_base_url,
            params=params,
            provider_key="openmeteo_air_quality",
        )
        fetched_at = datetime.now(UTC).isoformat()
        hourly = json_object(payload.get("hourly"))
        timeline = list(hourly.get("time") or [])
        pollutants = {
            name: self._series(hourly.get(name)) for name in self.AIR_QUALITY_VARIABLES
        }
        preview: list[dict[str, Any]] = []
        for index in range(min(6, len(timeline))):
            row: dict[str, Any] = {"time": timeline[index]}
            for key, values in pollutants.items():
                row[key] = values[index] if index < len(values) else None
            preview.append(row)
        partial = any(len(values) < len(timeline) for values in pollutants.values())
        result_status = "ok" if timeline else "valid_empty"
        if partial and timeline:
            result_status = "partial"
        return {
            "provider": "openmeteo",
            "kind": "air_quality_forecast",
            "source_url": self.air_quality_base_url,
            "fetched_at": fetched_at,
            "result_status": result_status,
            "result_type": "metadata",
            "partial": partial,
            "latitude": latitude,
            "longitude": longitude,
            "timezone": payload.get("timezone"),
            "hourly_preview": preview,
            "resolved_at": fetched_at,
            "observation_time": preview[0].get("time") if preview else None,
            "units": self._units(payload),
            "requested_variables": list(self.AIR_QUALITY_VARIABLES),
            "request_parameters": dict(params),
            "spatial_resolution": "point forecast",
            "coverage": {
                "type": "point",
                "latitude": latitude,
                "longitude": longitude,
            },
            "attribution": "Data from Open-Meteo",
        }

    # -------------------------------------------------------------------------
    @staticmethod
    def _units(payload: dict[str, Any]) -> dict[str, str]:
        units: dict[str, str] = {}
        for key in ("current_units", "hourly_units"):
            declared = json_object(payload.get(key))
            for name, unit in declared.items():
                if isinstance(unit, str) and unit.strip():
                    units.setdefault(name, unit.strip())
        return units

    # -------------------------------------------------------------------------
    @staticmethod
    def _series(value: object) -> list[Any]:
        return list(json_array(value))

    # -------------------------------------------------------------------------
    @staticmethod
    def _is_partial(
        *,
        timeline: list[Any],
        series: dict[str, list[Any]],
        current: dict[str, Any],
        current_variables: tuple[str, ...],
    ) -> bool:
        has_current_data = any(
            current.get(name) is not None for name in current_variables
        )
        if not timeline and not has_current_data:
            return False
        if timeline and any(len(values) < len(timeline) for values in series.values()):
            return True
        return any(
            name not in current or current.get(name) is None
            for name in current_variables
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def _result_status(
        *,
        timeline: list[Any],
        current: dict[str, Any],
        variables: tuple[str, ...],
        partial: bool,
    ) -> str:
        if timeline:
            return "partial" if partial else "ok"
        if any(current.get(name) is not None for name in variables):
            return "partial"
        return "valid_empty"

    # -------------------------------------------------------------------------
    def _get_json(
        self, *, endpoint: str, params: dict[str, str], provider_key: str
    ) -> dict[str, Any]:
        cache_key = f"{provider_key}:{urlencode(sorted(params.items()))}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        self._wait_for_rate_limit_slot(provider_key)
        url = f"{endpoint}?{urlencode(params)}"
        request = Request(url, headers={"User-Agent": self.user_agent})
        try:
            with urlopen(request, timeout=self.timeout_s) as response:
                payload = response.read().decode("utf-8")
        except (HTTPError, URLError, TimeoutError) as exc:
            raise OpenMeteoRequestError(f"Open-Meteo request failed: {exc}") from exc
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise OpenMeteoRequestError(
                "Open-Meteo response was not valid JSON."
            ) from exc
        if not is_json_object(data):
            raise OpenMeteoRequestError("Open-Meteo response payload is malformed.")
        self._cache_set(cache_key, data)
        return data

    # -------------------------------------------------------------------------
    def _cache_get(self, cache_key: str) -> dict[str, Any] | None:
        with self._lock:
            cached = self._cache.get(cache_key)
            if cached is None:
                return None
            ts, payload = cached
            if time.time() - ts > self.cache_ttl_s:
                self._cache.pop(cache_key, None)
                return None
            return dict(payload)

    # -------------------------------------------------------------------------
    def _cache_set(self, cache_key: str, payload: dict[str, Any]) -> None:
        with self._lock:
            self._cache[cache_key] = (time.time(), payload)

    # -------------------------------------------------------------------------
    def _wait_for_rate_limit_slot(self, key: str) -> None:
        with self._lock:
            now = time.time()
            previous = self._last_call_by_key.get(key, 0.0)
            delay = self.min_call_interval_s - (now - previous)
        if delay > 0:
            time.sleep(delay)
        with self._lock:
            self._last_call_by_key[key] = time.time()
