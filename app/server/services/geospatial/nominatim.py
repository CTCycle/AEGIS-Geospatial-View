from __future__ import annotations

from server.common.typing import is_json_array, is_json_object, json_object

import asyncio
import json
import math
import re
import socket
import threading
import time
import unicodedata
from collections import OrderedDict
from datetime import UTC, datetime
from difflib import SequenceMatcher
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from server.common.constants import (
    NOMINATIM_REVERSE_PATH,
    NOMINATIM_SEARCH_PATH,
)
from server.common.logger import logger
from server.configurations import get_server_settings


###############################################################################
class NominatimService:
    GENERIC_QUERY_DESCRIPTORS = frozenset(
        {
            "site",
            "location",
            "place",
            "facility",
            "premises",
            "campus",
            "office",
            "headquarters",
            "hq",
            "district",
            "neighborhood",
            "neighbourhood",
            "quarter",
            "borough",
            "area",
            "zona",
            "quartiere",
        }
    )
    ACRONYM_STOP_WORDS = frozenset(
        {"a", "an", "and", "at", "de", "del", "di", "la", "of", "the"}
    )

    # -------------------------------------------------------------------------
    def __init__(
        self, user_agent: str | None = None, timeout: float | None = None
    ) -> None:
        settings = get_server_settings().nominatim
        self.base_url = settings.base_url
        self.user_agent = user_agent or settings.user_agent
        default_timeout = settings.timeout
        self.timeout = timeout if timeout is not None else default_timeout
        self._request_lock = threading.Lock()
        self._last_request_started_at = 0.0
        self._min_request_interval_s = 1.0
        self._search_cache: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
        self._reverse_cache: OrderedDict[str, dict[str, Any] | None] = OrderedDict()
        self._max_cache_entries = 128

    # -------------------------------------------------------------------------
    async def extract_coordinates(
        self,
        address: str | None,
        city: str | None,
        country_name: str | None,
        country_code: str | None,
        limit: int = 5,
        expected_location_type: str | None = None,
    ) -> dict[str, Any] | None:
        queries = self.compose_query_variants(address, city, country_name)
        if not queries:
            return None
        effective_limit = max(1, min(10, int(limit or 1)))
        ranked: list[dict[str, Any]] = []
        selected_query = queries[0]
        fetched_at = datetime.now(UTC)
        for candidate_query in queries:
            params: dict[str, str] = {
                "q": candidate_query,
                "format": "jsonv2",
                "addressdetails": "1",
                "namedetails": "1",
                # Prefer a stable validation language while retaining the
                # provider's alternate names in ``namedetails``.  This lets
                # the resolver accept user-language names without depending
                # on the server's locale or on one display-name spelling.
                "accept-language": "en",
                "limit": str(effective_limit),
            }
            if country_code:
                params["countrycodes"] = country_code.lower()
            response = await asyncio.to_thread(self.perform_request, params)
            if not response:
                continue
            ranked = self.rank_candidates(
                response,
                address=address or "",
                city=city,
                country_name=country_name,
                country_code=country_code,
                query=candidate_query,
                expected_location_type=expected_location_type,
                fetched_at=fetched_at,
            )
            if ranked:
                selected_query = candidate_query
                break
        if not ranked:
            return None
        selected = dict(ranked[0])
        ambiguous_candidates = self._find_ambiguous_candidates(
            ranked,
            expected_location_type=expected_location_type,
            query=selected_query,
            has_parent_context=bool(
                city
                or country_name
                or country_code
                or any("," in item for item in queries)
            ),
        )
        if ambiguous_candidates:
            selected["ambiguous_candidates"] = ambiguous_candidates
        return selected

    # -------------------------------------------------------------------------
    def compose_query_variants(
        self,
        address: str | None,
        city: str | None,
        country_name: str | None,
    ) -> list[str]:
        """Build bounded provider queries for names and common descriptions.

        Facility descriptions and acronyms are often indexed differently from
        the phrase emitted by an extraction model.  The original complete
        query always runs first; reduced and acronym forms are only attempted
        when that query returns no usable candidates.
        """

        primary = self.compose_query(address, city, country_name)
        if not primary:
            return []
        variants = [primary]
        address_tokens = self.tokenize(address)
        core_tokens = [
            token
            for token in address_tokens
            if token not in self.GENERIC_QUERY_DESCRIPTORS
        ]
        core_address = " ".join(core_tokens)
        if core_address and self.normalize_component(core_address) != self.normalize_component(
            address or ""
        ):
            reduced = self.compose_query(core_address, city, country_name)
            if reduced and self.normalize_component(reduced) not in {
                self.normalize_component(item) for item in variants
            }:
                variants.append(reduced)
        acronym_tokens = [
            token for token in core_tokens if token not in self.ACRONYM_STOP_WORDS
        ]
        acronym = "".join(token[0] for token in acronym_tokens if token)
        if len(acronym) >= 3:
            acronym_query = self.compose_query(acronym, city, country_name)
            if acronym_query and self.normalize_component(acronym_query) not in {
                self.normalize_component(item) for item in variants
            }:
                variants.append(acronym_query)
        return variants

    # -------------------------------------------------------------------------
    def _find_ambiguous_candidates(
        self,
        ranked: list[dict[str, Any]],
        *,
        expected_location_type: str | None,
        query: str,
        has_parent_context: bool,
    ) -> list[dict[str, Any]]:
        """Return close, distinct candidates at the requested granularity."""

        if len(ranked) < 2:
            return []
        expected = str(expected_location_type or "").strip().lower()
        city_types = {"city", "town", "village", "municipality", "hamlet"}
        administrative_types = {
            "country",
            "state",
            "region",
            "county",
            "province",
            "administrative",
        }

        def city_level(candidate: dict[str, Any]) -> bool:
            candidate_type = str(
                candidate.get("selected_result_type") or ""
            ).lower()
            if candidate_type in city_types:
                candidate_text = self._candidate_text(candidate)
                return self.compute_token_overlap(
                    self.tokenize(query), self.tokenize(candidate_text)
                ) >= 0.6
            if candidate_type not in {"administrative", "boundary"}:
                return False
            address_type = str(
                candidate.get("selected_address_type") or ""
            ).lower()
            if address_type and address_type not in city_types:
                return False
            address: dict[str, Any] = json_object(candidate.get("address"))
            locality = next(
                (
                    str(address.get(key) or "")
                    for key in ("city", "town", "village", "municipality")
                    if address.get(key)
                ),
                "",
            )
            return bool(locality) and self.compute_token_overlap(
                self.tokenize(locality), self.tokenize(query)
            ) >= 0.8

        if expected in {"city", "municipality"}:
            same_level_candidates = [
                candidate for candidate in ranked if city_level(candidate)
            ]
        elif expected in {"region", "state", "province", "county"}:
            same_level_candidates = [
                candidate
                for candidate in ranked
                if str(candidate.get("selected_result_type") or "").lower()
                in administrative_types
                and str(candidate.get("selected_result_type") or "").lower()
                != "country"
            ]
        elif expected in {"address", "poi", "street"}:
            same_level_candidates = [
                candidate
                for candidate in ranked
                if str(candidate.get("selected_result_class") or "").lower()
                not in {"administrative", "boundary"}
            ]
        elif expected in {"neighborhood", "neighbourhood", "district"}:
            same_level_candidates = [
                candidate
                for candidate in ranked
                if self._district_candidate(candidate)
            ]
        elif expected == "country":
            same_level_candidates = [
                candidate
                for candidate in ranked
                if str(candidate.get("selected_result_type") or "").lower()
                == "country"
            ]
        else:
            first_type = str(ranked[0].get("selected_result_type") or "").lower()
            same_level_candidates = [
                candidate
                for candidate in ranked
                if first_type
                and str(candidate.get("selected_result_type") or "").lower()
                == first_type
            ]
        same_level_candidates = self._deduplicate_named_entities(
            same_level_candidates
        )
        if len(same_level_candidates) < 2:
            return []

        first = same_level_candidates[0]
        second = next(
            (
                candidate
                for candidate in same_level_candidates[1:]
                if not self._same_point(first, candidate)
            ),
            None,
        )
        if second is None:
            return []
        first_confidence = float(first.get("confidence") or 0.0)
        second_confidence = float(second.get("confidence") or 0.0)
        confidence_gap = abs(first_confidence - second_confidence)
        first_importance = float(first.get("geocoder_importance") or 0.0)
        second_importance = float(second.get("geocoder_importance") or 0.0)
        provider_importance_gap = first_importance - second_importance
        # An unqualified city name is ambiguous when same-level candidates
        # remain comparably supported.  A large provider-importance gap plus
        # a strong top confidence is deterministic evidence for a dominant
        # candidate; this avoids stopping on well-ranked global places while
        # preserving clarification for close candidates such as Cambridge.
        if not has_parent_context:
            if first_confidence >= 0.8 and provider_importance_gap >= 0.25:
                return []
            confidence_gap = 0.0
        if has_parent_context and confidence_gap >= 0.08:
            return []
        first_label = str(first.get("display_name") or "").strip()
        second_label = str(second.get("display_name") or "").strip()
        if not first_label or not second_label or first_label == second_label:
            return []
        return [
            {"display_name": first_label, "lat": first.get("lat"), "lon": first.get("lon")},
            {"display_name": second_label, "lat": second.get("lat"), "lon": second.get("lon")},
        ]

    # -------------------------------------------------------------------------
    @staticmethod
    def _candidate_text(candidate: dict[str, Any]) -> str:
        parts = [str(candidate.get("display_name") or "")]
        for field in ("address", "namedetails"):
            values = candidate.get(field)
            if is_json_object(values):
                parts.extend(str(value) for value in values.values())
        return " ".join(part for part in parts if part).strip()

    # -------------------------------------------------------------------------
    @staticmethod
    def _same_point(left: dict[str, Any], right: dict[str, Any]) -> bool:
        try:
            return (
                abs(float(left.get("lat") or 0.0) - float(right.get("lat") or 0.0))
                < 0.01
                and abs(
                    float(left.get("lon") or 0.0)
                    - float(right.get("lon") or 0.0)
                )
                < 0.01
            )
        except (TypeError, ValueError):
            return False

    # -------------------------------------------------------------------------
    def _deduplicate_named_entities(
        self, candidates: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        distinct: list[dict[str, Any]] = []
        for candidate in candidates:
            if any(
                self._same_named_entity(candidate, existing)
                for existing in distinct
            ):
                continue
            distinct.append(candidate)
        return distinct

    # -------------------------------------------------------------------------
    def _same_named_entity(
        self, left: dict[str, Any], right: dict[str, Any]
    ) -> bool:
        """Recognize alternate geocoder representations of one locality.

        A boundary result and a point result can describe the same city while
        differing by a postcode or centroid.  Treating those as competing
        places creates false clarification prompts.  Require the locality,
        country, and at least one administrative parent to agree so separate
        same-named cities remain ambiguous.
        """

        locality_keys = ("city", "town", "village", "municipality")
        parent_keys = (
            "county",
            "state_district",
            "state",
            "region",
            "province",
        )

        def components(candidate: dict[str, Any]) -> tuple[str, str, str]:
            address = json_object(candidate.get("address"))
            locality = next(
                (
                    str(address.get(key) or "")
                    for key in locality_keys
                    if address.get(key)
                ),
                "",
            )
            country = str(address.get("country") or "")
            parent = next(
                (
                    str(address.get(key) or "")
                    for key in parent_keys
                    if address.get(key)
                ),
                "",
            )
            return (
                self.normalize_component(locality),
                self.normalize_component(country),
                self.normalize_component(parent),
            )

        left_locality, left_country, left_parent = components(left)
        right_locality, right_country, right_parent = components(right)
        return bool(
            left_locality
            and left_parent
            and left_locality == right_locality
            and left_country
            and left_country == right_country
            and left_parent == right_parent
        )

    # -------------------------------------------------------------------------
    async def extract_bbox_from_coordinates(
        self,
        latitude: float,
        longitude: float,
    ) -> list[float] | None:
        params = {
            "lat": f"{latitude:.8f}",
            "lon": f"{longitude:.8f}",
            "format": "jsonv2",
            "zoom": "18",
            "polygon_geojson": "0",
            "addressdetails": "0",
        }
        response = await asyncio.to_thread(self.perform_reverse_request, params)
        if not response:
            return None
        bounding_box = response.get("boundingbox")
        if not is_json_array(bounding_box) or len(bounding_box) != 4:
            return None
        try:
            south = float(bounding_box[0])
            north = float(bounding_box[1])
            west = float(bounding_box[2])
            east = float(bounding_box[3])
        except TypeError, ValueError:
            return None
        return [west, south, east, north]

    # -------------------------------------------------------------------------
    def compose_query(
        self, address: str | None, city: str | None, country_name: str | None
    ) -> str:
        normalized_address = (address or "").strip()
        components: list[str] = [normalized_address] if normalized_address else []
        normalized_city = self.normalize_component(city or "")
        if normalized_city and normalized_city not in self.normalize_component(
            normalized_address
        ):
            components.append(city or "")
        if country_name:
            normalized_components = self.normalize_component(" ".join(components))
            normalized_country = self.normalize_component(country_name)
            if normalized_country and normalized_country not in normalized_components:
                components.append(country_name)
        return ", ".join(component for component in components if component)

    # -------------------------------------------------------------------------
    def perform_request(self, params: dict[str, str]) -> list[dict[str, Any]]:
        cache_key = urlencode(sorted(params.items()))
        cached = self._cache_get(self._search_cache, cache_key)
        if cached is not None:
            return [dict(item) for item in cached]
        data = self._perform_json_request(
            url=f"{self.base_url}?{urlencode(params)}",
            cache_key=cache_key,
            cache=self._search_cache,
            request_kind="search",
        )
        if not is_json_array(data):
            return []
        return [item for item in data if is_json_object(item)]

    # -------------------------------------------------------------------------
    def perform_reverse_request(self, params: dict[str, str]) -> dict[str, Any] | None:
        reverse_url = self.resolve_reverse_url()
        cache_key = urlencode(sorted(params.items()))
        cached = self._cache_get(self._reverse_cache, cache_key)
        if cached is not None:
            return dict(cached) if is_json_object(cached) else None
        data = self._perform_json_request(
            url=f"{reverse_url}?{urlencode(params)}",
            cache_key=cache_key,
            cache=self._reverse_cache,
            request_kind="reverse",
        )
        if is_json_object(data):
            return data
        return None

    # -------------------------------------------------------------------------
    def _perform_json_request(
        self,
        *,
        url: str,
        cache_key: str,
        cache: OrderedDict[str, Any],
        request_kind: str,
    ) -> Any:
        self._wait_for_rate_limit_slot()
        request = Request(url, headers={"User-Agent": self.user_agent})
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = response.read()
        except (HTTPError, URLError, socket.timeout, TimeoutError) as exc:
            logger.warning("Nominatim %s request failed: %s", request_kind, exc)
            return None
        try:
            data = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            logger.warning(
                "Nominatim %s response parsing failed: %s", request_kind, exc
            )
            return None
        self._cache_set(cache, cache_key, data)
        return data

    # -------------------------------------------------------------------------
    def _wait_for_rate_limit_slot(self) -> None:
        with self._request_lock:
            now = time.monotonic()
            remaining = self._min_request_interval_s - (
                now - self._last_request_started_at
            )
            if remaining > 0:
                time.sleep(remaining)
            self._last_request_started_at = time.monotonic()

    # -------------------------------------------------------------------------
    def _cache_get(self, cache: OrderedDict[str, Any], key: str) -> Any:
        with self._request_lock:
            if key not in cache:
                return None
            cache.move_to_end(key)
            return cache[key]

    # -------------------------------------------------------------------------
    def _cache_set(self, cache: OrderedDict[str, Any], key: str, value: Any) -> None:
        with self._request_lock:
            cache[key] = value
            cache.move_to_end(key)
            while len(cache) > self._max_cache_entries:
                cache.popitem(last=False)

    # -------------------------------------------------------------------------
    def format_result(
        self,
        data: dict[str, Any],
        *,
        address: str | None,
        city: str | None,
        country_name: str | None,
        country_code: str | None,
        query: str,
        fetched_at: datetime | None = None,
    ) -> dict[str, Any] | None:
        try:
            latitude = float(data["lat"])
            longitude = float(data["lon"])
        except KeyError, TypeError, ValueError:
            return None
        result: dict[str, Any] = {
            "lat": latitude,
            "lon": longitude,
            "source": "nominatim",
            "selected_result_type": str(data.get("type") or ""),
            "selected_result_class": str(data.get("class") or ""),
            "selected_address_type": str(data.get("addresstype") or ""),
            "display_name": data.get("display_name"),
        }
        address_data = data.get("address")
        if is_json_object(address_data):
            result["address"] = dict(address_data)
        namedetails = data.get("namedetails")
        if is_json_object(namedetails):
            result["namedetails"] = dict(namedetails)
        if fetched_at is not None:
            result.update(
                {
                    "provider": "nominatim",
                    "source_url": self.base_url,
                    "fetched_at": fetched_at.isoformat(),
                }
            )
        bounding_box = data.get("boundingbox")
        if is_json_array(bounding_box) and len(bounding_box) == 4:
            try:
                south = float(bounding_box[0])
                north = float(bounding_box[1])
                west = float(bounding_box[2])
                east = float(bounding_box[3])
                result["bbox"] = [west, south, east, north]
                result["bbox_source"] = "nominatim"
            except TypeError, ValueError:
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
        try:
            result["geocoder_importance"] = float(data["importance"])
        except KeyError, TypeError, ValueError:
            pass
        return result

    # -------------------------------------------------------------------------
    def _location_type_matches(
        self,
        *,
        expected_location_type: str | None,
        data: dict[str, Any],
        address: str | None,
        query: str,
    ) -> float:
        expected = str(expected_location_type or "").strip().lower()
        if not expected:
            return 1.0
        class_name = str(data.get("class") or "").lower()
        type_name = str(data.get("type") or "").lower()
        address_data = data.get("address")
        if not is_json_object(address_data):
            address_data = {}
        if expected == "coordinates":
            return 3.0
        if expected in {"neighborhood", "neighbourhood", "district"}:
            if self._district_candidate(data):
                return 3.0
            return 0.0
        address_type = str(data.get("addresstype") or "").strip().lower()
        if expected in {"city", "municipality"} and address_type in {
            "country",
            "state",
            "region",
            "county",
            "province",
        }:
            # Nominatim can return an administrative boundary whose generic
            # ``type`` is ``administrative`` even though it is a parent
            # region.  The explicit address type is the safer granularity
            # signal for rejecting that downgrade.
            return 0.0
        if expected in {"poi", "address"}:
            if class_name in {"amenity", "tourism", "building", "shop", "highway"}:
                return 3.0
            if class_name in {"boundary", "administrative"} or type_name in {
                "city",
                "state",
                "region",
                "county",
            }:
                return 0.0
            return 2.0
        if expected == "city" and type_name in {
            "city",
            "town",
            "village",
            "municipality",
        }:
            return 3.0
        if expected in {"city", "municipality"} and type_name in {
            "administrative",
            "boundary",
        }:
            locality = next(
                (
                    str(address_data.get(key) or "")
                    for key in (
                        "city",
                        "town",
                        "village",
                        "municipality",
                    )
                    if address_data.get(key)
                ),
                "",
            )
            candidate_text = self._candidate_text(data)
            target_tokens = self.tokenize(address) or self.tokenize(query)
            if locality and (
                self.compute_token_overlap(
                    self.tokenize(locality), self.tokenize(query)
                )
                >= 0.8
                or self.compute_token_overlap(
                    target_tokens, self.tokenize(candidate_text)
                )
                >= 0.8
            ):
                # Some geocoders represent a city boundary as an administrative
                # result while still returning the city in address details. It
                # remains the specific city target and must outrank its parent.
                return 3.0
            if target_tokens and (
                self.compute_token_overlap(
                    target_tokens, self.tokenize(candidate_text)
                )
                >= 0.8
            ):
                # Some localized geocoder responses omit a city address field
                # but put the requested locality in the display name.
                return 3.0
            return 0.0
        if expected in {"city", "municipality"} and type_name in {
            "country",
            "state",
            "region",
            "county",
            "province",
        }:
            # A parent result must never outrank a more specific city result.
            return 0.0
        if expected == "region" and type_name in {"state", "region", "county"}:
            return 3.0
        if expected in {"region", "state", "province", "county"} and type_name in {
            "administrative",
            "boundary",
        }:
            return 2.0
        return 1.0

    # -------------------------------------------------------------------------
    @staticmethod
    def _district_candidate(data: dict[str, Any]) -> bool:
        district_types = {
            "neighbourhood",
            "neighborhood",
            "suburb",
            "quarter",
            "city_district",
            "district",
            "borough",
            "locality",
        }
        result_type = str(data.get("type") or "").strip().lower()
        address_type = str(data.get("addresstype") or "").strip().lower()
        return result_type in district_types or address_type in district_types

    # -------------------------------------------------------------------------
    def rank_candidates(
        self,
        candidates: list[dict[str, Any]],
        *,
        address: str | None,
        city: str | None,
        country_name: str | None,
        country_code: str | None,
        query: str,
        expected_location_type: str | None,
        fetched_at: datetime | None = None,
    ) -> list[dict[str, Any]]:
        scored: list[tuple[float, float, dict[str, Any]]] = []
        normalized_query = self.normalize_component(query)
        for candidate in candidates:
            if not self._candidate_matches_requested_target(
                candidate,
                address=address,
                expected_location_type=expected_location_type,
            ):
                # Search providers frequently return a nearby child feature
                # when a named parent facility is not indexed under the
                # complete phrase.  A partial acronym hit is not sufficient
                # evidence that the child is the requested target.
                continue
            formatted = self.format_result(
                candidate,
                address=address,
                city=city,
                country_name=country_name,
                country_code=country_code,
                query=query,
                fetched_at=fetched_at,
            )
            if not is_json_object(formatted):
                continue
            display_name = self.normalize_component(
                str(candidate.get("display_name") or "")
            )
            text_bonus = (
                0.1 if normalized_query and normalized_query in display_name else 0.0
            )
            confidence = float(formatted.get("confidence") or 0.0)
            location_type_bonus = self._location_type_matches(
                expected_location_type=expected_location_type,
                data=candidate,
                address=address,
                query=query,
            )
            score = confidence + text_bonus + location_type_bonus
            scored.append((location_type_bonus, score, formatted))
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [item[2] for item in scored]

    # -------------------------------------------------------------------------
    def _candidate_matches_requested_target(
        self,
        candidate: dict[str, Any],
        *,
        address: str | None,
        expected_location_type: str | None,
    ) -> bool:
        """Require the requested named target to survive geocoder ranking.

        ``address`` is also used for POI names by the location resolver.  The
        provider query may return a child feature that shares only an acronym
        with the requested parent (for example, a shop or parking area).  For
        named POI/address targets, require all non-descriptor target tokens to
        appear in the provider's display name or alternate names.  This keeps
        query variants useful without allowing a nearby partial match to be
        promoted to a verified target.
        """

        expected = str(expected_location_type or "").strip().lower()
        if expected in {"neighborhood", "neighbourhood", "district"}:
            if not self._district_candidate(candidate):
                return False
            target_tokens = [
                token
                for token in self.tokenize(address)
                if token not in self.GENERIC_QUERY_DESCRIPTORS
            ]
            if not target_tokens:
                return False
            candidate_tokens = self.tokenize(self._candidate_text(candidate))
            return self.compute_token_overlap(target_tokens, candidate_tokens) >= 0.8
        if expected not in {"address", "poi", "street"}:
            return True
        target_tokens = self.tokenize(address)
        if not target_tokens:
            return False
        target_tokens = [
            token
            for token in target_tokens
            if token not in self.GENERIC_QUERY_DESCRIPTORS
        ]
        if not target_tokens:
            return False
        candidate_tokens = self.tokenize(self._candidate_text(candidate))
        return (
            self.compute_token_overlap(target_tokens, candidate_tokens) >= 0.8
        )

    # -------------------------------------------------------------------------
    def compute_confidence(
        self,
        *,
        data: dict[str, Any],
        address: str | None,
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
        granularity_score = self.derive_granularity_score(
            data.get("class"), data.get("type")
        )
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
            address=address or "",
            data=data,
        )
        if not math.isfinite(combined):
            return None
        if combined < 0.0:
            return 0.0
        if combined > 1.0:
            return 1.0
        return round(combined, 4)

    # -------------------------------------------------------------------------
    def derive_importance_score(self, importance: Any) -> float:
        try:
            value = float(importance)
        except TypeError, ValueError:
            return 0.55
        if value <= 0.0:
            return 0.05
        if value >= 1.0:
            return 1.0
        return max(0.05, min(1.0, value**0.3))

    # -------------------------------------------------------------------------
    def derive_text_match_score(
        self,
        data: dict[str, Any],
        *,
        address: str | None,
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
            display_alignment = self.compute_token_overlap(
                address_tokens, display_tokens
            )
            structured_alignment = self.compute_token_overlap(
                address_tokens, structured_tokens
            )
            if structured_alignment > max(display_alignment, 0.65):
                blended_alignment = (display_alignment * 0.4) + (
                    structured_alignment * 0.6
                )
                score += blended_alignment * address_weight
            else:
                score += display_alignment * address_weight
        if city_weight:
            score += (
                self.compute_city_alignment(city_tokens, data, display_tokens)
                * city_weight
            )
        if country_weight:
            score += (
                self.compute_country_alignment(
                    country_name,
                    country_code,
                    data,
                    normalized_display,
                )
                * country_weight
            )
        if query_weight:
            score += (
                self.compute_token_overlap(query_tokens, display_tokens) * query_weight
            )
        return score / total_weight

    # -------------------------------------------------------------------------
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

    # -------------------------------------------------------------------------
    def derive_bbox_score(self, bounding_box: Any) -> float:
        if not is_json_array(bounding_box) or len(bounding_box) != 4:
            return 0.5
        try:
            south = float(bounding_box[0])
            north = float(bounding_box[1])
            west = float(bounding_box[2])
            east = float(bounding_box[3])
        except TypeError, ValueError:
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

    # -------------------------------------------------------------------------
    def tokenize(self, value: str | None) -> list[str]:
        if not value:
            return []
        normalized_value = self.normalize_component(value)
        if not normalized_value:
            return []
        return [token for token in normalized_value.split() if token]

    # -------------------------------------------------------------------------
    def collect_address_tokens(self, data: dict[str, Any]) -> list[str]:
        address_data = data.get("address")
        if not is_json_object(address_data):
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

    # -------------------------------------------------------------------------
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

    # -------------------------------------------------------------------------
    def derive_structured_alignment_score(
        self,
        address: str | None,
        data: dict[str, Any],
    ) -> float:
        address_tokens = self.tokenize(address)
        if not address_tokens:
            return 0.0
        structured_tokens = self.collect_address_tokens(data)
        if not structured_tokens:
            return 0.0
        return self.compute_token_overlap(address_tokens, structured_tokens)

    # -------------------------------------------------------------------------
    def derive_house_number_score(
        self, address: str | None, data: dict[str, Any]
    ) -> float:
        address_tokens = self.tokenize(address)
        number_tokens = [token for token in address_tokens if token.isdigit()]
        if not number_tokens:
            return 0.5
        address_data = data.get("address")
        if not is_json_object(address_data):
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

    # -------------------------------------------------------------------------
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

    # -------------------------------------------------------------------------
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
        if not is_json_object(address_data):
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
            if (
                candidate
                and self.normalize_component(str(candidate)) == normalized_city
            ):
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

    # -------------------------------------------------------------------------
    def compute_country_alignment(
        self,
        country_name: str | None,
        country_code: str | None,
        data: dict[str, Any],
        normalized_display: str,
    ) -> float:
        address_data = data.get("address")
        if not is_json_object(address_data):
            address_data = {}
        expected_code = (country_code or "").lower()
        result_code = str(address_data.get("country_code", "")).lower()
        if expected_code and result_code:
            if expected_code == result_code:
                return 1.0
            return 0.35
        normalized_country = (
            self.normalize_component(country_name) if country_name else ""
        )
        if normalized_country:
            candidate = address_data.get("country")
            if (
                candidate
                and self.normalize_component(str(candidate)) == normalized_country
            ):
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

    # -------------------------------------------------------------------------
    def normalize_component(self, value: str) -> str:
        normalized = unicodedata.normalize("NFKD", value)
        ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
        # Geocoders commonly render acronyms with an interpunctuated form
        # (for example ``E.U.R.``) while the request uses ``EUR``.  Collapse
        # those internal dots before removing the remaining punctuation so
        # raw-span matching remains useful without hardcoding a place name.
        ascii_text = re.sub(
            r"(?<=[A-Za-z0-9])\.(?=[A-Za-z0-9])", "", ascii_text
        )
        ascii_text = re.sub(r"[^A-Za-z0-9]+", " ", ascii_text)
        return " ".join(ascii_text.lower().split())

    # -------------------------------------------------------------------------
    def compute_similarity_ratio(self, source: str, target: str) -> float:
        normalized_source = self.normalize_component(source)
        normalized_target = self.normalize_component(target)
        if not normalized_source or not normalized_target:
            return 0.0
        if normalized_source == normalized_target:
            return 1.0
        return SequenceMatcher(a=normalized_source, b=normalized_target).ratio()

    # -------------------------------------------------------------------------
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

    # -------------------------------------------------------------------------
    def resolve_reverse_url(self) -> str:
        normalized = self.base_url.rstrip("/")
        if normalized.endswith(NOMINATIM_SEARCH_PATH):
            base = normalized[: -len(NOMINATIM_SEARCH_PATH)]
            return f"{base}{NOMINATIM_REVERSE_PATH}"
        return f"{normalized}{NOMINATIM_REVERSE_PATH}"
