"""Open-Elevation service for fetching elevation data."""

from __future__ import annotations

import asyncio
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import json

from AEGIS.server.utils.constants import OPEN_ELEVATION_API_BASE_URL
from AEGIS.server.utils.logger import logger


__all__ = [
    "OpenElevationService",
    "OpenElevationError",
]


###############################################################################
class OpenElevationError(Exception):
    """Exception for Open-Elevation service failures."""


###############################################################################
class OpenElevationService:
    """Fetches elevation data from Open-Elevation API (no auth required).

    Open-Elevation provides free access to global DEM (Digital Elevation Model)
    data, returning elevation in meters for any coordinate on Earth.

    API Reference: https://open-elevation.com/
    """

    BASE_URL = OPEN_ELEVATION_API_BASE_URL

    def __init__(
        self,
        *,
        user_agent: str | None = None,
        timeout_s: float = 10.0,
    ) -> None:
        """Initialize Open-Elevation service.

        Args:
            user_agent: User agent string for API requests
            timeout_s: Request timeout in seconds
        """
        self.user_agent = user_agent or "AEGIS-OpenElevation/1.0"
        self.timeout_s = timeout_s

    # -------------------------------------------------------------------------
    async def get_elevation(self, lat: float, lon: float) -> dict[str, Any]:
        """Fetch elevation for a single coordinate.

        Args:
            lat: Latitude of the point
            lon: Longitude of the point

        Returns:
            Dictionary containing:
                - elevation: Elevation in meters
                - latitude: Original latitude
                - longitude: Original longitude
                - attribution: Data source attribution
        """
        result = await asyncio.to_thread(
            self._fetch_elevation,
            lat=lat,
            lon=lon,
        )
        return result

    # -------------------------------------------------------------------------
    async def get_elevation_batch(
        self, points: list[tuple[float, float]]
    ) -> list[dict[str, Any]]:
        """Fetch elevation for multiple coordinates.

        Args:
            points: List of (latitude, longitude) tuples

        Returns:
            List of elevation results for each point
        """
        if not points:
            return []

        result = await asyncio.to_thread(
            self._fetch_elevation_batch,
            points=points,
        )
        return result

    # -------------------------------------------------------------------------
    def _fetch_elevation(self, lat: float, lon: float) -> dict[str, Any]:
        """Fetch elevation from Open-Elevation API for a single point."""
        url = f"{self.BASE_URL}/lookup?locations={lat},{lon}"
        logger.debug("Fetching Open-Elevation: url=%s", url)

        request = Request(url, headers={"User-Agent": self.user_agent})

        try:
            with urlopen(request, timeout=self.timeout_s) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError) as exc:
            logger.warning("Open-Elevation request failed: %s", exc)
            return self._empty_response(lat, lon)
        except json.JSONDecodeError as exc:
            logger.warning("Open-Elevation response parse error: %s", exc)
            return self._empty_response(lat, lon)

        results = data.get("results") or []
        if not results:
            return self._empty_response(lat, lon)

        result = results[0]
        elevation = result.get("elevation")

        return {
            "elevation": float(elevation) if elevation is not None else None,
            "latitude": result.get("latitude", lat),
            "longitude": result.get("longitude", lon),
            "attribution": "Elevation data from Open-Elevation (SRTM/ASTER)",
        }

    # -------------------------------------------------------------------------
    def _fetch_elevation_batch(
        self, points: list[tuple[float, float]]
    ) -> list[dict[str, Any]]:
        """Fetch elevation for multiple points via POST request."""
        locations = [{"latitude": lat, "longitude": lon} for lat, lon in points]
        payload = json.dumps({"locations": locations}).encode("utf-8")

        url = f"{self.BASE_URL}/lookup"
        logger.debug(
            "Fetching Open-Elevation batch: url=%s, points=%d", url, len(points)
        )

        request = Request(
            url,
            data=payload,
            headers={
                "User-Agent": self.user_agent,
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urlopen(request, timeout=self.timeout_s) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError) as exc:
            logger.warning("Open-Elevation batch request failed: %s", exc)
            return [self._empty_response(lat, lon) for lat, lon in points]
        except json.JSONDecodeError as exc:
            logger.warning("Open-Elevation response parse error: %s", exc)
            return [self._empty_response(lat, lon) for lat, lon in points]

        results = data.get("results") or []
        parsed = []

        for i, result in enumerate(results):
            lat, lon = points[i] if i < len(points) else (None, None)
            elevation = result.get("elevation")
            parsed.append(
                {
                    "elevation": float(elevation) if elevation is not None else None,
                    "latitude": result.get("latitude", lat),
                    "longitude": result.get("longitude", lon),
                    "attribution": "Elevation data from Open-Elevation (SRTM/ASTER)",
                }
            )

        return parsed

    # -------------------------------------------------------------------------
    def _empty_response(self, lat: float, lon: float) -> dict[str, Any]:
        """Return an empty response when elevation cannot be fetched."""
        return {
            "elevation": None,
            "latitude": lat,
            "longitude": lon,
            "attribution": "Elevation data unavailable",
        }
