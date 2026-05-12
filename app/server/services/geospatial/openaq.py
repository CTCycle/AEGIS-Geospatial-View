"""OpenAQ service for fetching real-time air quality data."""

from __future__ import annotations

import asyncio
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import json

from server.common.constants import OPENAQ_API_BASE_URL
from server.common.logger import logger


__all__ = [
    "OpenAQService",
    "OpenAQServiceError",
    "OpenAQRequestError",
]


###############################################################################
class OpenAQServiceError(Exception):
    """Base exception for OpenAQ service failures."""


###############################################################################
class OpenAQRequestError(OpenAQServiceError):
    """Raised when OpenAQ API cannot fulfill the request."""


###############################################################################
class OpenAQService:
    """Fetches real-time air quality measurements from OpenAQ API.

    OpenAQ provides free access to air quality data from monitoring stations
    worldwide, including PM2.5, PM10, NO2, O3, SO2, CO measurements.

    API Reference: https://docs.openaq.org/
    """

    BASE_URL = OPENAQ_API_BASE_URL

    # Pollutants supported by OpenAQ
    SUPPORTED_POLLUTANTS = ("pm25", "pm10", "no2", "o3", "so2", "co", "bc")

    # Human-readable names for pollutants
    POLLUTANT_LABELS = {
        "pm25": "PM2.5 (Fine Particles)",
        "pm10": "PM10 (Coarse Particles)",
        "no2": "Nitrogen Dioxide (NO₂)",
        "o3": "Ozone (O₃)",
        "so2": "Sulfur Dioxide (SO₂)",
        "co": "Carbon Monoxide (CO)",
        "bc": "Black Carbon (BC)",
    }

    def __init__(
        self,
        *,
        api_key: str | None = None,
        user_agent: str | None = None,
        timeout_s: float = 15.0,
        max_locations: int = 10,
        default_radius_m: float = 25000.0,
    ) -> None:
        """Initialize OpenAQ service.

        Args:
            api_key: Optional OpenAQ API key
            user_agent: User agent string for API requests
            timeout_s: Request timeout in seconds
            max_locations: Maximum number of nearby locations to fetch
            default_radius_m: Default search radius in meters
        """
        self.api_key = (api_key or "").strip()
        self.user_agent = user_agent or "AEGIS-OpenAQ/1.0"
        self.timeout_s = timeout_s
        self.max_locations = max_locations
        self.default_radius_m = default_radius_m

    # -------------------------------------------------------------------------
    async def get_nearby_measurements(
        self,
        lat: float,
        lon: float,
        radius_m: float | None = None,
    ) -> dict[str, Any]:
        """Fetch air quality measurements from nearby monitoring stations.

        Args:
            lat: Latitude of search center
            lon: Longitude of search center
            radius_m: Search radius in meters (default: 25km)

        Returns:
            Dictionary containing:
                - locations: List of nearby monitoring stations with measurements
                - summary: Aggregated values for each pollutant
                - attribution: Data source attribution
        """
        search_radius = radius_m or self.default_radius_m
        radius_km = search_radius / 1000.0

        # Fetch nearby locations
        locations = await asyncio.to_thread(
            self._fetch_locations,
            lat=lat,
            lon=lon,
            radius_km=radius_km,
        )

        if not locations:
            return self._empty_response()

        # Aggregate measurements
        summary = self._aggregate_measurements(locations)

        return {
            "locations": locations,
            "summary": summary,
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
        radius_km: float,
    ) -> list[dict[str, Any]]:
        """Fetch locations with measurements from OpenAQ API."""
        # OpenAQ v3 uses coordinates parameter for nearby search
        params = {
            "coordinates": f"{lat},{lon}",
            "radius": int(radius_km * 1000),  # API expects meters
            "limit": self.max_locations,
            "order_by": "distance",
        }

        url = f"{self.BASE_URL}/locations?{urlencode(params)}"
        logger.debug("Fetching OpenAQ locations: url=%s", url)

        headers = {"User-Agent": self.user_agent}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        request = Request(url, headers=headers)

        try:
            with urlopen(request, timeout=self.timeout_s) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError) as exc:
            logger.warning("OpenAQ request failed: %s", exc)
            return []
        except json.JSONDecodeError as exc:
            logger.warning("OpenAQ response parse error: %s", exc)
            return []

        results = data.get("results") or []
        locations = []

        for location in results:
            parsed = self._parse_location(location)
            if parsed:
                locations.append(parsed)

        return locations

    # -------------------------------------------------------------------------
    def _parse_location(self, location: dict[str, Any]) -> dict[str, Any] | None:
        """Parse a location response from OpenAQ API."""
        location_id = location.get("id")
        name = location.get("name") or f"Station {location_id}"

        coordinates = location.get("coordinates") or {}
        lat = coordinates.get("latitude")
        lon = coordinates.get("longitude")

        if lat is None or lon is None:
            return None

        # Extract latest measurements from sensors
        sensors = location.get("sensors") or []
        measurements = {}

        for sensor in sensors:
            parameter = sensor.get("parameter") or {}
            param_name = (parameter.get("name") or "").lower().replace(".", "")

            # Get latest value
            latest = sensor.get("latest") or {}
            value = latest.get("value")

            if param_name and value is not None:
                measurements[param_name] = {
                    "value": float(value),
                    "unit": parameter.get("units") or "µg/m³",
                    "datetime": latest.get("datetime"),
                }

        if not measurements:
            return None

        return {
            "id": location_id,
            "name": name,
            "latitude": float(lat),
            "longitude": float(lon),
            "country": location.get("country", {}).get("name"),
            "city": location.get("locality"),
            "measurements": measurements,
            "distance_m": location.get("distance"),
        }

    # -------------------------------------------------------------------------
    def _aggregate_measurements(
        self, locations: list[dict[str, Any]]
    ) -> dict[str, dict[str, Any]]:
        """Aggregate measurements across all locations."""
        aggregates: dict[str, list[float]] = {}

        for location in locations:
            measurements = location.get("measurements") or {}
            for param, data in measurements.items():
                if param not in aggregates:
                    aggregates[param] = []
                value = data.get("value")
                if value is not None:
                    aggregates[param].append(float(value))

        summary = {}
        for param, values in aggregates.items():
            if not values:
                continue
            summary[param] = {
                "mean": sum(values) / len(values),
                "min": min(values),
                "max": max(values),
                "count": len(values),
                "label": self.POLLUTANT_LABELS.get(param, param.upper()),
            }

        return summary

    # -------------------------------------------------------------------------
    def _empty_response(self) -> dict[str, Any]:
        """Return an empty response when no data is available."""
        return {
            "locations": [],
            "summary": {},
            "attribution": "No air quality data available for this location",
            "provider": "openaq",
        }
