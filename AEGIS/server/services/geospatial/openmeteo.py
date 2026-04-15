from __future__ import annotations

import asyncio
import json
import threading
import time
from datetime import UTC, datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from AEGIS.server.configurations import get_server_settings


class OpenMeteoServiceError(Exception):
    """Base exception for Open-Meteo failures."""


class OpenMeteoRequestError(OpenMeteoServiceError):
    """Raised when Open-Meteo cannot fulfill a request."""


class OpenMeteoService:
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
        self.air_quality_base_url = air_quality_base_url or settings.air_quality_base_url
        self.user_agent = user_agent or settings.user_agent
        self.timeout_s = timeout_s if timeout_s is not None else settings.timeout
        self.cache_ttl_s = max(cache_ttl_s if cache_ttl_s is not None else settings.cache_ttl_s, 30.0)
        self.min_call_interval_s = max(
            min_call_interval_s if min_call_interval_s is not None else settings.min_call_interval_s,
            0.05,
        )
        self._lock = threading.Lock()
        self._last_call_by_key: dict[str, float] = {}
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}

    async def get_weather_forecast(self, *, latitude: float, longitude: float) -> dict[str, Any]:
        params = {
            "latitude": f"{latitude:.6f}",
            "longitude": f"{longitude:.6f}",
            "hourly": "temperature_2m,precipitation,weather_code",
            "current": "temperature_2m,precipitation,weather_code",
            "forecast_days": "3",
            "timezone": "auto",
        }
        payload = await asyncio.to_thread(
            self._get_json,
            endpoint=self.weather_base_url,
            params=params,
            provider_key="openmeteo_weather",
        )
        hourly = payload.get("hourly") if isinstance(payload.get("hourly"), dict) else {}
        timeline = list(hourly.get("time") or [])
        temperature = list(hourly.get("temperature_2m") or [])
        precipitation = list(hourly.get("precipitation") or [])
        weather_code = list(hourly.get("weather_code") or [])
        preview: list[dict[str, Any]] = []
        for index in range(min(6, len(timeline))):
            preview.append(
                {
                    "time": timeline[index],
                    "temperature_2m": temperature[index] if index < len(temperature) else None,
                    "precipitation": precipitation[index] if index < len(precipitation) else None,
                    "weather_code": weather_code[index] if index < len(weather_code) else None,
                }
            )
        return {
            "provider": "openmeteo",
            "kind": "weather_forecast",
            "latitude": latitude,
            "longitude": longitude,
            "timezone": payload.get("timezone"),
            "current": payload.get("current") if isinstance(payload.get("current"), dict) else {},
            "hourly_preview": preview,
            "resolved_at": datetime.now(UTC).isoformat(),
            "attribution": "Data from Open-Meteo",
        }

    async def get_air_quality_forecast(self, *, latitude: float, longitude: float) -> dict[str, Any]:
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
        hourly = payload.get("hourly") if isinstance(payload.get("hourly"), dict) else {}
        timeline = list(hourly.get("time") or [])
        pollutants = {
            "pm2_5": list(hourly.get("pm2_5") or []),
            "pm10": list(hourly.get("pm10") or []),
            "nitrogen_dioxide": list(hourly.get("nitrogen_dioxide") or []),
            "ozone": list(hourly.get("ozone") or []),
            "sulphur_dioxide": list(hourly.get("sulphur_dioxide") or []),
            "carbon_monoxide": list(hourly.get("carbon_monoxide") or []),
        }
        preview: list[dict[str, Any]] = []
        for index in range(min(6, len(timeline))):
            row: dict[str, Any] = {"time": timeline[index]}
            for key, values in pollutants.items():
                row[key] = values[index] if index < len(values) else None
            preview.append(row)
        return {
            "provider": "openmeteo",
            "kind": "air_quality_forecast",
            "latitude": latitude,
            "longitude": longitude,
            "timezone": payload.get("timezone"),
            "hourly_preview": preview,
            "resolved_at": datetime.now(UTC).isoformat(),
            "attribution": "Data from Open-Meteo",
        }

    def _get_json(self, *, endpoint: str, params: dict[str, str], provider_key: str) -> dict[str, Any]:
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
            raise OpenMeteoRequestError("Open-Meteo response was not valid JSON.") from exc
        if not isinstance(data, dict):
            raise OpenMeteoRequestError("Open-Meteo response payload is malformed.")
        self._cache_set(cache_key, data)
        return data

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

    def _cache_set(self, cache_key: str, payload: dict[str, Any]) -> None:
        with self._lock:
            self._cache[cache_key] = (time.time(), payload)

    def _wait_for_rate_limit_slot(self, key: str) -> None:
        with self._lock:
            now = time.time()
            previous = self._last_call_by_key.get(key, 0.0)
            delay = self.min_call_interval_s - (now - previous)
        if delay > 0:
            time.sleep(delay)
        with self._lock:
            self._last_call_by_key[key] = time.time()
