"""OpenAQ service for fetching real-time air quality data."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from server.common.constants import OPENAQ_API_BASE_URL
from server.common.logger import logger
from server.common.typing import is_json_array, is_json_object, json_array, json_object

__all__ = [
    "OpenAQService",
    "OpenAQServiceError",
    "OpenAQRequestError",
    "OpenAQAuthError",
    "OpenAQRateLimitError",
    "OpenAQInvalidQueryError",
    "OpenAQMalformedPayloadError",
]

###############################################################################
class OpenAQServiceError(Exception):
    """Base exception for OpenAQ service failures."""


###############################################################################
class OpenAQRequestError(OpenAQServiceError):
    """Raised when OpenAQ API cannot fulfill the request."""


###############################################################################
class OpenAQAuthError(OpenAQServiceError):
    """Raised when OpenAQ rejects the configured API key."""


###############################################################################
class OpenAQRateLimitError(OpenAQServiceError):
    """Raised when OpenAQ applies a rate limit."""


###############################################################################
class OpenAQInvalidQueryError(OpenAQServiceError):
    """Raised when OpenAQ rejects a deterministic query."""


###############################################################################
class OpenAQMalformedPayloadError(OpenAQServiceError):
    """Raised when OpenAQ returns an invalid response shape."""


JsonRequester = Callable[[str, dict[str, str]], Any]

###############################################################################
class OpenAQService:
    """Fetch nearby OpenAQ locations and their latest sensor observations."""

    BASE_URL = OPENAQ_API_BASE_URL
    SUPPORTED_POLLUTANTS = ("pm25", "pm10", "no2", "o3", "so2", "co", "bc")
    POLLUTANT_LABELS = {
        "pm25": "PM2.5 (Fine Particles)",
        "pm10": "PM10 (Coarse Particles)",
        "no2": "Nitrogen Dioxide (NO₂)",
        "o3": "Ozone (O₃)",
        "so2": "Sulfur Dioxide (SO₂)",
        "co": "Carbon Monoxide (CO)",
        "bc": "Black Carbon (BC)",
    }

    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        api_key: str | None = None,
        user_agent: str | None = None,
        timeout_s: float = 15.0,
        max_locations: int = 10,
        default_radius_m: float = 25000.0,
        requester: JsonRequester | None = None,
    ) -> None:
        self.api_key = (api_key or "").strip()
        self.user_agent = user_agent or "AEGIS-OpenAQ/1.0"
        self.timeout_s = timeout_s
        self.max_locations = max(1, min(int(max_locations), 100))
        self.default_radius_m = default_radius_m
        self.requester = requester or self._request_json_from_network

    # -------------------------------------------------------------------------
    async def get_nearby_measurements(
        self,
        lat: float,
        lon: float,
        radius_m: float | None = None,
    ) -> dict[str, Any]:
        search_radius = max(
            1.0,
            min(
                float(radius_m if radius_m is not None else self.default_radius_m),
                25000.0,
            ),
        )
        locations = await asyncio.to_thread(
            self._fetch_locations,
            lat=lat,
            lon=lon,
            radius_m=search_radius,
        )
        if not locations:
            return self._empty_response()
        return {
            "locations": locations,
            "summary": self._aggregate_measurements(locations),
            "center": {"latitude": lat, "longitude": lon},
            "radius_m": search_radius,
            "attribution": "Data from OpenAQ (openaq.org)",
            "provider": "openaq",
        }

    # -------------------------------------------------------------------------
    def _fetch_locations(
        self,
        lat: float,
        lon: float,
        radius_m: float,
    ) -> list[dict[str, Any]]:
        params: dict[str, str | int] = {
            "coordinates": f"{lat},{lon}",
            "radius": max(1, min(int(round(radius_m)), 25000)),
            "limit": self.max_locations,
            "page": 1,
            "order_by": "id",
        }
        url = f"{self.BASE_URL}/locations?{urlencode(params)}"
        data = self.requester(url, self._headers())
        results = self._response_results(data, endpoint="locations")
        locations: list[dict[str, Any]] = []
        for raw_location in results:
            location = json_object(raw_location)
            if not location:
                continue
            parsed = self._parse_location(location)
            if parsed is None:
                continue
            location_id = parsed["id"]
            if not json_object(parsed.get("sensor_metadata")):
                sensors_url = (
                    f"{self.BASE_URL}/locations/{location_id}/sensors?"
                    f"{urlencode({'limit': 100, 'page': 1})}"
                )
                parsed["sensor_metadata"] = self._sensor_metadata_from_response(
                    self.requester(sensors_url, self._headers())
                )
            latest_url = (
                f"{self.BASE_URL}/locations/{location_id}/latest?"
                f"{urlencode({'limit': 100, 'page': 1})}"
            )
            latest_payload = self.requester(latest_url, self._headers())
            self._attach_latest_measurements(parsed, latest_payload)
            if parsed.get("measurements"):
                locations.append(parsed)
        return locations

    # -------------------------------------------------------------------------
    def _parse_location(self, location: dict[str, Any]) -> dict[str, Any] | None:
        location_id = location.get("id")
        if location_id is None:
            return None
        coordinates = json_object(location.get("coordinates"))
        sensors: dict[str, dict[str, Any]] = {}
        for raw_instrument in json_array(location.get("instruments")):
            instrument = json_object(raw_instrument)
            for raw_sensor in json_array(instrument.get("sensors")):
                sensor = json_object(raw_sensor)
                sensor_id = sensor.get("id")
                if sensor_id is not None:
                    sensors[str(sensor_id)] = self._sensor_metadata(sensor)
        if not sensors:
            for raw_sensor in json_array(location.get("sensors")):
                sensor = json_object(raw_sensor)
                sensor_id = sensor.get("id")
                if sensor_id is not None:
                    sensors[str(sensor_id)] = self._sensor_metadata(sensor)
        country = json_object(location.get("country"))
        return {
            "id": location_id,
            "name": location.get("name") or f"Station {location_id}",
            "latitude": self._float_or_none(coordinates.get("latitude")),
            "longitude": self._float_or_none(coordinates.get("longitude")),
            "country": country.get("name") or location.get("country"),
            "city": location.get("locality"),
            "measurements": {},
            "distance_m": location.get("distance") or location.get("distance_m"),
            "sensor_metadata": sensors,
        }

    # -------------------------------------------------------------------------
    def _sensor_metadata_from_response(self, payload: object) -> dict[str, dict[str, Any]]:
        sensors: dict[str, dict[str, Any]] = {}
        for raw_sensor in self._response_results(payload, endpoint="sensors"):
            sensor = json_object(raw_sensor)
            sensor_id = sensor.get("id")
            if sensor_id is not None:
                sensors[str(sensor_id)] = self._sensor_metadata(sensor)
        return sensors

    # -------------------------------------------------------------------------
    def _attach_latest_measurements(
        self, location: dict[str, Any], payload: object
    ) -> None:
        measurements: dict[str, dict[str, Any]] = {}
        sensor_metadata = json_object(location.get("sensor_metadata"))
        for raw_measurement in self._response_results(
            payload, endpoint="latest measurements"
        ):
            measurement = json_object(raw_measurement)
            if not measurement:
                continue
            sensor_id = str(
                measurement.get("sensorsId")
                or measurement.get("sensorId")
                or ""
            )
            metadata = json_object(sensor_metadata.get(sensor_id))
            raw_parameter = measurement.get("parameter")
            parameter = json_object(raw_parameter)
            parameter_name = (
                metadata.get("parameter")
                or parameter.get("name")
                or (raw_parameter if isinstance(raw_parameter, str) else None)
            )
            normalized_name = self._normalize_parameter(parameter_name)
            value = self._float_or_none(measurement.get("value"))
            if not normalized_name or value is None:
                continue
            timestamp = json_object(measurement.get("datetime"))
            coordinates = json_object(measurement.get("coordinates"))
            if location.get("latitude") is None:
                location["latitude"] = self._float_or_none(coordinates.get("latitude"))
            if location.get("longitude") is None:
                location["longitude"] = self._float_or_none(coordinates.get("longitude"))
            measurements[normalized_name] = {
                "value": value,
                "unit": metadata.get("units") or parameter.get("units") or "µg/m³",
                "datetime": timestamp.get("utc")
                or timestamp.get("local")
                or measurement.get("datetime"),
                "sensor_id": sensor_id or None,
            }
        location["measurements"] = measurements

    # -------------------------------------------------------------------------
    @staticmethod
    def _sensor_metadata(sensor: dict[str, Any]) -> dict[str, Any]:
        parameter = json_object(sensor.get("parameter"))
        return {
            "parameter": parameter.get("name"),
            "units": parameter.get("units"),
        }

    # -------------------------------------------------------------------------
    @staticmethod
    def _normalize_parameter(value: object) -> str:
        return (
            str(value or "")
            .strip()
            .lower()
            .replace(".", "")
            .replace("-", "")
            .replace(" ", "")
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def _float_or_none(value: object) -> float | None:
        if not isinstance(value, int | float | str):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    # -------------------------------------------------------------------------
    @staticmethod
    def _response_results(payload: object, *, endpoint: str) -> list[object]:
        if not is_json_object(payload) or not is_json_array(payload.get("results")):
            raise OpenAQMalformedPayloadError(
                f"OpenAQ {endpoint} response is missing a results array."
            )
        return json_array(payload.get("results"))

    # -------------------------------------------------------------------------
    def _headers(self) -> dict[str, str]:
        headers = {"User-Agent": self.user_agent}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

    # -------------------------------------------------------------------------
    def _request_json_from_network(self, url: str, headers: dict[str, str]) -> Any:
        logger.debug("Fetching OpenAQ endpoint: %s", url)
        request = Request(url, headers=headers)
        try:
            with urlopen(request, timeout=self.timeout_s) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code in {401, 403}:
                raise OpenAQAuthError("OpenAQ rejected the configured API key.") from exc
            if exc.code == 429:
                raise OpenAQRateLimitError("OpenAQ rate limit exceeded.") from exc
            if exc.code in {400, 404, 409, 410, 422}:
                raise OpenAQInvalidQueryError("OpenAQ rejected the requested query.") from exc
            raise OpenAQRequestError("OpenAQ request failed.") from exc
        except (URLError, TimeoutError, OSError) as exc:
            logger.warning("OpenAQ request failed.")
            raise OpenAQRequestError("OpenAQ request failed.") from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            logger.warning("OpenAQ response parse failed.")
            raise OpenAQMalformedPayloadError("OpenAQ returned malformed JSON.") from exc

    # -------------------------------------------------------------------------
    def _aggregate_measurements(
        self, locations: list[dict[str, Any]]
    ) -> dict[str, dict[str, Any]]:
        aggregates: dict[str, list[float]] = {}
        for location in locations:
            measurements = json_object(location.get("measurements"))
            for param, data in measurements.items():
                value = self._float_or_none(json_object(data).get("value"))
                if value is not None:
                    aggregates.setdefault(param, []).append(value)
        summary: dict[str, dict[str, Any]] = {}
        for param, values in aggregates.items():
            summary[param] = {
                "mean": sum(values) / len(values),
                "min": min(values),
                "max": max(values),
                "count": len(values),
                "label": self.POLLUTANT_LABELS.get(param, param.upper()),
            }
        return summary

    # -------------------------------------------------------------------------
    @staticmethod
    def _empty_response() -> dict[str, Any]:
        return {
            "locations": [],
            "summary": {},
            "attribution": "No air quality data available for this location",
            "provider": "openaq",
            "result_status": "valid_empty",
        }
