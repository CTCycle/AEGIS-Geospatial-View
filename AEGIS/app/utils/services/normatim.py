from __future__ import annotations

import asyncio
import json
import logging
import math
import socket
import unicodedata
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
        formatted = self.format_result(
            response[0],
            address=address,
            city=city,
            country_name=country_name,
            country_code=country_code,
            query=params["q"],
        )
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
    def format_result(
        self,
        data: dict[str, Any],
        *,
        address: str,
        city: str | None,
        country_name: str | None,
        country_code: str | None,
        query: str,
    ) -> dict[str, Any] | None:
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
        confidence = self.compute_confidence(
            data=data,
            address=address,
            city=city,
            country_name=country_name,
            country_code=country_code,
            query=query,
        )
        if confidence is not None:
            result["confidence"] = confidence
        return result

    #-----------------------------------------------------------------------------
    def compute_confidence(
        self,
        *,
        data: dict[str, Any],
        address: str,
        city: str | None,
        country_name: str | None,
        country_code: str | None,
        query: str,
    ) -> float | None:
        importance_score = self.derive_importance_score(data.get("importance"))
        text_score = self.derive_text_match_score(
            data.get("display_name"),
            address=address,
            city=city,
            country_name=country_name,
            country_code=country_code,
            query=query,
        )
        granularity_score = self.derive_granularity_score(data.get("class"), data.get("type"))
        bounding_box = data.get("boundingbox")
        bbox_score = self.derive_bbox_score(bounding_box) if bounding_box else 0.5
        combined = (
            (importance_score * 0.4)
            + (text_score * 0.3)
            + (granularity_score * 0.2)
            + (bbox_score * 0.1)
        )
        if not math.isfinite(combined):
            return None
        if combined < 0.0:
            return 0.0
        if combined > 1.0:
            return 1.0
        return round(combined, 4)

    #-----------------------------------------------------------------------------
    def derive_importance_score(self, importance: Any) -> float:
        try:
            value = float(importance)
        except (TypeError, ValueError):
            return 0.55
        if value <= 0.0:
            return 0.05
        if value >= 1.0:
            return 1.0
        return max(0.05, min(1.0, value ** 0.3))

    #-----------------------------------------------------------------------------
    def derive_text_match_score(
        self,
        display_name: Any,
        *,
        address: str,
        city: str | None,
        country_name: str | None,
        country_code: str | None,
        query: str,
    ) -> float:
        components: list[str] = []
        for value in (address, city, country_name, country_code, query):
            if value:
                components.append(self.normalize_component(value))
        if not components:
            return 0.5
        normalized_display = self.normalize_component(str(display_name)) if display_name else ""
        matches = 0
        for component in components:
            if component and component in normalized_display:
                matches += 1
        if matches == 0 and normalized_display:
            overlap = self.compute_overlap_ratio(components[0], normalized_display)
            return max(0.2, min(1.0, overlap))
        return matches / len(components)

    #-----------------------------------------------------------------------------
    def derive_granularity_score(self, place_class: Any, place_type: Any) -> float:
        class_name = str(place_class or "").lower()
        type_name = str(place_type or "").lower()
        if class_name == "building":
            return 1.0
        if class_name == "amenity":
            return 0.9
        if class_name == "highway":
            return 0.8
        if class_name == "shop":
            return 0.85
        if class_name == "tourism":
            return 0.75
        if class_name == "railway":
            return 0.7
        if class_name == "place":
            if type_name in {"house", "building", "neighbourhood", "suburb"}:
                return 0.85
            if type_name in {"quarter", "town", "village"}:
                return 0.7
            if type_name in {"city", "municipality"}:
                return 0.65
            if type_name in {"county", "state", "region"}:
                return 0.5
        if class_name in {"boundary", "administrative"}:
            if type_name in {"administrative", "protected_area"}:
                return 0.55
            return 0.45
        if class_name == "natural":
            return 0.35
        if class_name == "landuse":
            return 0.4
        return 0.55

    #-----------------------------------------------------------------------------
    def derive_bbox_score(self, bounding_box: Any) -> float:
        if not isinstance(bounding_box, list) or len(bounding_box) != 4:
            return 0.5
        try:
            south = float(bounding_box[0])
            north = float(bounding_box[1])
            west = float(bounding_box[2])
            east = float(bounding_box[3])
        except (TypeError, ValueError):
            return 0.5
        lat_span = abs(north - south)
        lon_span = abs(east - west)
        if lat_span <= 0.0 or lon_span <= 0.0:
            return 0.6
        area = lat_span * lon_span
        if area <= 0.0001:
            return 1.0
        if area <= 0.0005:
            return 0.85
        if area <= 0.001:
            return 0.75
        if area <= 0.005:
            return 0.6
        if area <= 0.05:
            return 0.5
        return 0.35

    #-----------------------------------------------------------------------------
    def normalize_component(self, value: str) -> str:
        normalized = unicodedata.normalize("NFKD", value)
        ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
        return " ".join(ascii_text.lower().split())

    #-----------------------------------------------------------------------------
    def compute_overlap_ratio(self, source: str, target: str) -> float:
        normalized_source = self.normalize_component(source)
        normalized_target = self.normalize_component(target)
        if not normalized_source or not normalized_target:
            return 0.0
        if normalized_source in normalized_target:
            return len(normalized_source) / len(normalized_target)
        if normalized_target in normalized_source:
            return len(normalized_target) / len(normalized_source)
        return 0.0
