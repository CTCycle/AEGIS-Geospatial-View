from __future__ import annotations

import asyncio
import json
import logging
import math
import socket
import unicodedata
from difflib import SequenceMatcher
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
            data,
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
            (importance_score * 0.25)
            + (text_score * 0.45)
            + (granularity_score * 0.2)
            + (bbox_score * 0.1)
        )
        combined = self.apply_quality_boosts(
            combined,
            text_score=text_score,
            granularity_score=granularity_score,
            bbox_score=bbox_score,
            importance_score=importance_score,
            address=address,
            data=data,
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
        data: dict[str, Any],
        *,
        address: str,
        city: str | None,
        country_name: str | None,
        country_code: str | None,
        query: str,
    ) -> float:
        normalized_display = self.normalize_component(str(data.get("display_name", "")))
        display_tokens = normalized_display.split()
        structured_tokens = self.collect_address_tokens(data)
        address_tokens = self.tokenize(address)
        city_tokens = self.tokenize(city)
        query_tokens = self.tokenize(query)
        address_weight = 0.6 if address_tokens else 0.0
        city_weight = 0.25 if city_tokens else 0.0
        country_weight = 0.15 if country_name or country_code else 0.0
        query_weight = 0.1 if query_tokens and not address_tokens else 0.0
        total_weight = address_weight + city_weight + country_weight + query_weight
        if total_weight == 0.0:
            return 0.5
        score = 0.0
        if address_weight:
            display_alignment = self.compute_token_overlap(address_tokens, display_tokens)
            structured_alignment = self.compute_token_overlap(address_tokens, structured_tokens)
            if structured_alignment > max(display_alignment, 0.65):
                blended_alignment = (
                    (display_alignment * 0.4) + (structured_alignment * 0.6)
                )
                score += blended_alignment * address_weight
            else:
                score += display_alignment * address_weight
        if city_weight:
            score += self.compute_city_alignment(city_tokens, data, display_tokens) * city_weight
        if country_weight:
            score += self.compute_country_alignment(
                country_name,
                country_code,
                data,
                normalized_display,
            ) * country_weight
        if query_weight:
            score += self.compute_token_overlap(query_tokens, display_tokens) * query_weight
        return score / total_weight

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
    def tokenize(self, value: str | None) -> list[str]:
        if not value:
            return []
        normalized_value = self.normalize_component(value)
        if not normalized_value:
            return []
        return [token for token in normalized_value.split() if token]

    #-----------------------------------------------------------------------------
    def collect_address_tokens(self, data: dict[str, Any]) -> list[str]:
        address_data = data.get("address")
        if not isinstance(address_data, dict):
            return []
        tokens: list[str] = []
        for key in (
            "house_number",
            "road",
            "pedestrian",
            "footway",
            "residential",
            "neighbourhood",
            "suburb",
            "city",
            "town",
            "village",
            "state",
            "county",
        ):
            value = address_data.get(key)
            if value:
                tokens.extend(self.tokenize(str(value)))
        return tokens

    #-----------------------------------------------------------------------------
    def compute_token_overlap(
        self,
        tokens: list[str],
        reference_tokens: list[str],
    ) -> float:
        if not tokens:
            return 0.0
        if not reference_tokens:
            return 0.5
        direct_matches = len(set(tokens) & set(reference_tokens))
        if direct_matches == len(tokens):
            return 1.0
        available_references = list(reference_tokens)
        fuzzy_matches = 0.0
        for token in tokens:
            best_ratio = 0.0
            best_index = -1
            for index, reference in enumerate(available_references):
                ratio = self.compute_similarity_ratio(token, reference)
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_index = index
            if best_ratio >= 0.95:
                fuzzy_matches += 1.0
            elif best_ratio >= 0.7:
                fuzzy_matches += best_ratio
            if best_index >= 0:
                available_references.pop(best_index)
        direct_ratio = direct_matches / len(tokens)
        fuzzy_ratio = fuzzy_matches / len(tokens)
        aggregate_ratio = self.compute_similarity_ratio(
            " ".join(tokens), " ".join(reference_tokens)
        )
        score = max(direct_ratio, fuzzy_ratio, aggregate_ratio)
        if score <= 0.0:
            overlap = self.compute_overlap_ratio(
                " ".join(tokens), " ".join(reference_tokens)
            )
            score = max(score, overlap)
        if score <= 0.0:
            return 0.2
        if score > 1.0:
            return 1.0
        return max(0.2, score)

    #-----------------------------------------------------------------------------
    def derive_structured_alignment_score(
        self,
        address: str,
        data: dict[str, Any],
    ) -> float:
        address_tokens = self.tokenize(address)
        if not address_tokens:
            return 0.0
        structured_tokens = self.collect_address_tokens(data)
        if not structured_tokens:
            return 0.0
        return self.compute_token_overlap(address_tokens, structured_tokens)

    #-----------------------------------------------------------------------------
    def derive_house_number_score(self, address: str, data: dict[str, Any]) -> float:
        address_tokens = self.tokenize(address)
        number_tokens = [token for token in address_tokens if token.isdigit()]
        if not number_tokens:
            return 0.5
        address_data = data.get("address")
        if not isinstance(address_data, dict):
            return 0.2
        candidate = address_data.get("house_number")
        if not candidate:
            return 0.2
        normalized_candidate = self.normalize_component(str(candidate))
        if not normalized_candidate:
            return 0.2
        for token in number_tokens:
            if token == normalized_candidate:
                return 1.0
            if self.compute_similarity_ratio(token, normalized_candidate) >= 0.9:
                return 1.0
        return 0.2

    #-----------------------------------------------------------------------------
    def apply_quality_boosts(
        self,
        combined: float,
        *,
        text_score: float,
        granularity_score: float,
        bbox_score: float,
        importance_score: float,
        address: str,
        data: dict[str, Any],
    ) -> float:
        adjusted = combined
        structured_score = self.derive_structured_alignment_score(address, data)
        house_score = self.derive_house_number_score(address, data)
        if structured_score >= 0.75 and bbox_score >= 0.85:
            adjusted = max(adjusted, 0.78)
        if structured_score >= 0.85 and house_score >= 0.9:
            adjusted = max(adjusted, 0.86)
        if bbox_score >= 0.95 and granularity_score >= 0.8 and house_score >= 0.9:
            adjusted = max(adjusted, 0.9)
        if text_score >= 0.7 and bbox_score >= 0.85:
            adjusted = max(adjusted, 0.82)
        if importance_score <= 0.1 and structured_score >= 0.9 and bbox_score >= 0.85:
            adjusted = max(adjusted, 0.88)
        return adjusted

    #-----------------------------------------------------------------------------
    def compute_city_alignment(
        self,
        city_tokens: list[str],
        data: dict[str, Any],
        display_tokens: list[str],
    ) -> float:
        if not city_tokens:
            return 0.5
        normalized_city = " ".join(city_tokens)
        address_data = data.get("address")
        if not isinstance(address_data, dict):
            address_data = {}
        for key in (
            "city",
            "town",
            "village",
            "hamlet",
            "municipality",
            "county",
            "state_district",
            "suburb",
        ):
            candidate = address_data.get(key)
            if candidate and self.normalize_component(str(candidate)) == normalized_city:
                return 1.0
        display_set = set(display_tokens)
        city_set = set(city_tokens)
        intersection = city_set & display_set
        if intersection:
            return len(intersection) / len(city_set)
        display_string = " ".join(display_tokens)
        similarity = self.compute_similarity_ratio(normalized_city, display_string)
        if similarity > 0.0:
            return max(0.2, min(1.0, similarity))
        overlap = self.compute_overlap_ratio(normalized_city, display_string)
        if overlap <= 0.0:
            return 0.2
        return max(0.2, min(1.0, overlap))

    #-----------------------------------------------------------------------------
    def compute_country_alignment(
        self,
        country_name: str | None,
        country_code: str | None,
        data: dict[str, Any],
        normalized_display: str,
    ) -> float:
        address_data = data.get("address")
        if not isinstance(address_data, dict):
            address_data = {}
        expected_code = (country_code or "").lower()
        result_code = str(address_data.get("country_code", "")).lower()
        if expected_code and result_code:
            if expected_code == result_code:
                return 1.0
            return 0.35
        normalized_country = self.normalize_component(country_name) if country_name else ""
        if normalized_country:
            candidate = address_data.get("country")
            if candidate and self.normalize_component(str(candidate)) == normalized_country:
                return 0.9
        if normalized_country and normalized_country in normalized_display:
            return 0.8
        if normalized_country:
            similarity = self.compute_similarity_ratio(
                normalized_country, normalized_display
            )
            if similarity > 0.0:
                return max(0.2, min(1.0, similarity))
            overlap = self.compute_overlap_ratio(normalized_country, normalized_display)
            if overlap <= 0.0:
                return 0.2
            return max(0.2, min(1.0, overlap))
        return 0.5

    #-----------------------------------------------------------------------------
    def normalize_component(self, value: str) -> str:
        normalized = unicodedata.normalize("NFKD", value)
        ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
        return " ".join(ascii_text.lower().split())

    #-----------------------------------------------------------------------------
    def compute_similarity_ratio(self, source: str, target: str) -> float:
        normalized_source = self.normalize_component(source)
        normalized_target = self.normalize_component(target)
        if not normalized_source or not normalized_target:
            return 0.0
        if normalized_source == normalized_target:
            return 1.0
        return SequenceMatcher(a=normalized_source, b=normalized_target).ratio()

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
