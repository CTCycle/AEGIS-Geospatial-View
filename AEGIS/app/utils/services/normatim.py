from __future__ import annotations

import asyncio
import json
import logging
import socket
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

LOGGER = logging.getLogger(__name__)

###############################################################################
class NormatimService:
    base_url = "https://nominatim.openstreetmap.org/search"
    def __init__(self, user_agent: str | None = None, timeout: float = 10.0) -> None:
        self.user_agent = (
            user_agent
            or "AEGIS-Geographics/1.0 (contact: support@aegis-geographics.local)"
        )
        self.timeout = timeout

    #-----------------------------------------------------------------------------
    async def extract_coordinates(
        self,
        address: str,
        city: str | None,
        country_name: str | None,
        country_code: str | None,
        limit: int = 1,
    ) -> dict[str, Any] | None:
        if not address:
            return None
        params: dict[str, str] = {
            "q": self.compose_query(address, city, country_name),
            "format": "jsonv2",
            "addressdetails": "1",
            "limit": str(limit),
        }
        if country_code:
            params["countrycodes"] = country_code.lower()
        response = await asyncio.to_thread(self.perform_request, params)
        if not response:
            return None
        formatted = self.format_result(response[0])
        return formatted

    #-----------------------------------------------------------------------------
    def compose_query(self, address: str, city: str | None, country_name: str | None) -> str:
        components = [address]
        if city and city.lower() not in address.lower():
            components.append(city)
        if country_name:
            lowered = " ".join(components).lower()
            if country_name.lower() not in lowered:
                components.append(country_name)
        return ", ".join(component for component in components if component)

    #-----------------------------------------------------------------------------
    def perform_request(self, params: dict[str, str]) -> list[dict[str, Any]]:
        url = f"{self.base_url}?{urlencode(params)}"
        request = Request(url, headers={"User-Agent": self.user_agent})
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = response.read()
        except (HTTPError, URLError, socket.timeout, TimeoutError) as exc:
            LOGGER.warning("Normatim request failed: %s", exc)
            return []
        try:
            data = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            LOGGER.warning("Normatim response parsing failed: %s", exc)
            return []
        if not isinstance(data, list):
            return []
        return [item for item in data if isinstance(item, dict)]

    #-----------------------------------------------------------------------------
    def format_result(self, data: dict[str, Any]) -> dict[str, Any] | None:
        try:
            latitude = float(data["lat"])
            longitude = float(data["lon"])
        except (KeyError, TypeError, ValueError):
            return None
        result: dict[str, Any] = {
            "lat": latitude,
            "lon": longitude,
            "source": "nominatim",
        }
        bounding_box = data.get("boundingbox")
        if isinstance(bounding_box, list) and len(bounding_box) == 4:
            try:
                south = float(bounding_box[0])
                north = float(bounding_box[1])
                west = float(bounding_box[2])
                east = float(bounding_box[3])
                result["bbox"] = [south, west, north, east]
            except (TypeError, ValueError):
                pass
        importance = data.get("importance")
        if importance is not None:
            try:
                confidence = float(importance)
            except (TypeError, ValueError):
                confidence = None
            if confidence is not None:
                if confidence < 0.0:
                    confidence = 0.0
                if confidence > 1.0:
                    confidence = 1.0
                result["confidence"] = confidence
        return result
