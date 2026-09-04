from __future__ import annotations

import math
import re
from typing import Any

from server.common.typing import json_object

from typing import Sequence

from server.common.logger import logger as LOGGER
from server.domain.agent.decision import (
    ClarificationRequest,
    LocationResolutionProvenance,
    ResolvedLocation,
)
from server.contracts.extraction import LocationSignal
from server.services.geospatial.nominatim import NominatimService


###############################################################################
class LocationResolver:
    SPECIFICITY_BY_SIGNAL_TYPE = {
        "coordinates": 4,
        "address": 3,
        "poi": 3,
        "street": 3,
        "neighborhood": 2,
        "district": 2,
        "municipality": 2,
        "city": 2,
        "deictic": 2,
        "county": 1,
        "province": 1,
        "state": 1,
        "region": 1,
        "country": 1,
    }
    ADMINISTRATIVE_RESULT_TYPES = frozenset(
        {"country", "state", "region", "county", "province", "administrative"}
    )
    CITY_RESULT_TYPES = frozenset(
        {"city", "town", "village", "municipality", "hamlet"}
    )
    GENERIC_TARGET_DESCRIPTORS = frozenset(
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
        }
    )

    # -------------------------------------------------------------------------
    def __init__(self, *, nominatim_service: NominatimService | None = None) -> None:
        self.nominatim_service = nominatim_service or NominatimService()

    # -------------------------------------------------------------------------
    async def resolve_location_signals(
        self,
        location_signals: list[LocationSignal],
        memory_snapshot: dict[str, Any],
    ) -> ResolvedLocation | ClarificationRequest:
        if not location_signals:
            active = json_object(memory_snapshot.get("active_location"))
            remembered = self._location_from_memory(active)
            if remembered is not None:
                return remembered
            if active:
                LOGGER.warning(
                    "Ignoring invalid active location memory label=%s",
                    active.get("label"),
                )
            if active and not remembered:
                return ClarificationRequest(
                    question="I could not safely reuse the remembered location. Which location should I use?",
                    reason="Remembered location is missing valid coordinates.",
                    missing_fields=["location"],
                )
            return ClarificationRequest(
                question="Which location should I use?",
                reason="No resolvable location signal found.",
                missing_fields=["location"],
            )

        coordinate_signals = [
            signal
            for signal in location_signals
            if signal.signal_type == "coordinates"
            and self._valid_coordinates(signal.latitude, signal.longitude)
        ]
        if coordinate_signals:
            if not self._same_coordinate_signals(coordinate_signals):
                return self.build_ambiguity_question(
                    coordinate_signals,
                    reason="Multiple coordinate targets were provided.",
                )
            resolved = await self._resolve_signal(coordinate_signals[0])
            if isinstance(resolved, ResolvedLocation):
                return resolved
            return ClarificationRequest(
                question="I could not use those coordinates. Which location should I use?",
                reason="The explicit coordinate target could not be resolved.",
                missing_fields=["location"],
            )

        explicit_signals = [
            signal
            for signal in location_signals
            if signal.signal_type != "coordinates" and signal.raw_value.strip()
        ]
        if not explicit_signals:
            return ClarificationRequest(
                question="I could not resolve that location. Can you provide a city or coordinates?",
                reason="Geocoder did not return a valid candidate.",
                missing_fields=["location"],
            )

        highest_specificity = max(
            self.SPECIFICITY_BY_SIGNAL_TYPE.get(signal.signal_type, 0)
            for signal in explicit_signals
        )
        target_signals = [
            signal
            for signal in explicit_signals
            if self.SPECIFICITY_BY_SIGNAL_TYPE.get(signal.signal_type, 0)
            == highest_specificity
        ]
        target_signals = self._dedupe_signals(target_signals)
        if len(target_signals) > 1:
            return self.build_ambiguity_question(
                target_signals,
                reason="Multiple same-level location targets were provided.",
            )

        target = target_signals[0]
        parent_signals = [signal for signal in explicit_signals if signal is not target]
        if self._has_conflicting_parent_signals(parent_signals):
            return self.build_ambiguity_question(
                parent_signals,
                reason="The location includes conflicting parent regions or countries.",
            )

        resolved = await self._resolve_signal(target, context_signals=parent_signals)
        if isinstance(resolved, (ResolvedLocation, ClarificationRequest)):
            return resolved

        return ClarificationRequest(
            question=(
                f"I could not safely resolve {target.normalized_value or target.raw_value}. "
                "Can you provide a city, country, or coordinates?"
            ),
            reason=(
                "The geocoder returned no candidate matching the most specific target "
                "and its parent context."
            ),
            missing_fields=["location"],
        )

    # -------------------------------------------------------------------------
    def score_location_matches(
        self, location_signals: Sequence[LocationSignal]
    ) -> list[LocationSignal]:
        return sorted(
            location_signals,
            key=lambda item: (
                self.SPECIFICITY_BY_SIGNAL_TYPE.get(item.signal_type, 0),
                item.confidence,
            ),
            reverse=True,
        )

    # -------------------------------------------------------------------------
    def _dedupe_signals(self, signals: Sequence[LocationSignal]) -> list[LocationSignal]:
        seen: set[tuple[str, str]] = set()
        result: list[LocationSignal] = []
        for signal in signals:
            value = self._normalize_text(signal.normalized_value or signal.raw_value)
            key = (signal.signal_type, value)
            if not value or key in seen:
                continue
            seen.add(key)
            result.append(signal)
        return result

    # -------------------------------------------------------------------------
    def _has_conflicting_parent_signals(
        self, signals: Sequence[LocationSignal]
    ) -> bool:
        by_specificity: dict[int, set[str]] = {}
        for signal in signals:
            specificity = self.SPECIFICITY_BY_SIGNAL_TYPE.get(signal.signal_type, 0)
            value = self._normalize_text(signal.normalized_value or signal.raw_value)
            if not value:
                continue
            by_specificity.setdefault(specificity, set()).add(value)
        return any(len(values) > 1 for values in by_specificity.values())

    # -------------------------------------------------------------------------
    def _same_coordinate_signals(self, signals: Sequence[LocationSignal]) -> bool:
        if not signals:
            return True
        first = signals[0]
        return all(self._same_resolved_point(first, signal) for signal in signals[1:])

    def _same_resolved_point(self, left: LocationSignal, right: LocationSignal) -> bool:
        if any(
            value is None
            for value in (
                left.latitude,
                left.longitude,
                right.latitude,
                right.longitude,
            )
        ):
            return False
        left_latitude = left.latitude
        left_longitude = left.longitude
        right_latitude = right.latitude
        right_longitude = right.longitude
        assert left_latitude is not None and left_longitude is not None
        assert right_latitude is not None and right_longitude is not None
        return (
            abs(float(left_latitude) - float(right_latitude)) < 0.01
            and abs(float(left_longitude) - float(right_longitude)) < 0.01
        )

    # -------------------------------------------------------------------------
    def _same_resolved_location(
        self, left: ResolvedLocation, right: ResolvedLocation
    ) -> bool:
        return (
            abs(float(left.latitude) - float(right.latitude)) < 0.01
            and abs(float(left.longitude) - float(right.longitude)) < 0.01
        )

    # -------------------------------------------------------------------------
    async def _resolve_signal(
        self,
        signal: LocationSignal,
        *,
        context_signals: Sequence[LocationSignal] = (),
    ) -> ResolvedLocation | ClarificationRequest | None:
        if self._valid_coordinates(signal.latitude, signal.longitude):
            return ResolvedLocation(
                label=signal.normalized_value or signal.raw_value,
                latitude=float(signal.latitude),
                longitude=float(signal.longitude),
                source=signal.source,
                confidence=signal.confidence,
                location_type=signal.signal_type,
            )
        target_value = (signal.normalized_value or signal.raw_value).strip()
        country = self._context_value(context_signals, {"country"})
        city = self._context_value(
            context_signals, {"city", "municipality", "town", "village"}
        )
        regional_values = self._context_values(
            context_signals,
            {"region", "state", "province", "county"},
        )
        address = target_value
        if regional_values and signal.signal_type != "country":
            address = ", ".join([target_value, *regional_values])
        if signal.signal_type == "country":
            country = None
            city = None
            address = target_value
        geocoded = await self.nominatim_service.extract_coordinates(
            address=address,
            city=(
                city
                if signal.signal_type
                in {"address", "poi", "street", "neighborhood", "district"}
                else None
            ),
            country_name=country,
            country_code=None,
            expected_location_type=signal.signal_type,
        )
        geocoded = json_object(geocoded)
        if not geocoded:
            return None
        ambiguous_candidates = geocoded.get("ambiguous_candidates")
        if isinstance(ambiguous_candidates, list):
            options = [
                str(json_object(item).get("display_name") or "").strip()
                for item in ambiguous_candidates
                if json_object(item).get("display_name")
            ]
            if len(options) > 1:
                return ClarificationRequest(
                    question=f"Which location do you mean: {', '.join(options)}?",
                    reason="The geocoder returned multiple same-level candidates with similar confidence.",
                    missing_fields=["location"],
                )
        if not self._candidate_matches_target(
            geocoded,
            signal=signal,
            context_signals=context_signals,
        ):
            LOGGER.warning(
                "Rejecting geocoder candidate that does not match target=%s type=%s display=%s",
                target_value,
                geocoded.get("selected_result_type"),
                geocoded.get("display_name"),
            )
            return None
        latitude = self._number(geocoded.get("lat"))
        longitude = self._number(geocoded.get("lon"))
        if not self._valid_coordinates(latitude, longitude):
            return None
        bbox = self._valid_bbox(geocoded.get("bbox"))
        geocoder_type = self._normalize_text(
            str(geocoded.get("selected_result_type") or "")
        )
        resolved_type = geocoder_type or None
        if (
            signal.signal_type in {"city", "municipality"}
            and geocoder_type in self.ADMINISTRATIVE_RESULT_TYPES
            and (
                self._address_component(
                    geocoded, "city", "town", "village", "municipality"
                )
                or self._contains_location_text(
                    self._normalize_text(str(geocoded.get("display_name") or "")),
                    self._normalize_text(signal.normalized_value or signal.raw_value),
                )
            )
        ):
            # A city boundary may be returned as an administrative object. The
            # validated locality in its address details preserves the explicit
            # target granularity for viewport policy and telemetry.
            resolved_type = signal.signal_type
        try:
            return ResolvedLocation(
                label=str(geocoded.get("display_name") or signal.raw_value),
                latitude=latitude,
                longitude=longitude,
                source="geocoder",
                confidence=self._bounded_confidence(
                    geocoded.get("confidence"), signal.confidence
                ),
                location_type=resolved_type,
                location_class=str(geocoded.get("selected_result_class") or "")
                or None,
                country=self._address_component(geocoded, "country"),
                city=self._address_component(
                    geocoded, "city", "town", "village", "municipality"
                ),
                address=self._address_component(
                    geocoded, "house_number", "road", "pedestrian"
                ),
                bbox=bbox,
                bbox_source=str(geocoded.get("bbox_source") or "") or None,
                provenance=self._provenance_from_geocoded(geocoded),
            )
        except (TypeError, ValueError):
            return None

    # -------------------------------------------------------------------------
    def _candidate_matches_target(
        self,
        candidate: dict[str, Any],
        *,
        signal: LocationSignal,
        context_signals: Sequence[LocationSignal],
    ) -> bool:
        target = self._normalize_text(signal.normalized_value or signal.raw_value)
        display = self._normalize_text(str(candidate.get("display_name") or ""))
        address = json_object(candidate.get("address"))
        namedetails = json_object(candidate.get("namedetails"))
        structured = self._normalize_text(
            " ".join(
                [
                    *(str(value) for value in address.values()),
                    *(str(value) for value in namedetails.values()),
                ]
            )
        )
        candidate_text = f"{display} {structured}".strip()
        if not target or not self._target_matches_candidate(
            candidate_text,
            target,
            signal.signal_type,
        ):
            return False

        result_type = self._normalize_text(str(candidate.get("selected_result_type") or ""))
        result_class = self._normalize_text(str(candidate.get("selected_result_class") or ""))
        address_type = self._normalize_text(
            str(candidate.get("selected_address_type") or "")
        )
        if signal.signal_type == "country":
            if result_type and result_type != "country":
                return False
        if signal.signal_type in {"city", "municipality"}:
            if address_type in {
                "country",
                "state",
                "region",
                "county",
                "province",
            }:
                return False
            candidate_city = self._normalize_text(
                str(
                    address.get("city")
                    or address.get("town")
                    or address.get("village")
                    or address.get("municipality")
                    or ""
                )
            )
            if result_type in self.ADMINISTRATIVE_RESULT_TYPES and (
                (
                    not candidate_city
                    and not self._contains_location_text(candidate_text, target)
                )
                or (
                    candidate_city
                    and not (
                        self._contains_location_text(target, candidate_city)
                        or self._contains_location_text(candidate_text, target)
                    )
                )
            ):
                return False
            if result_class in {"administrative", "boundary"} and result_type in {
                "country",
                "state",
                "region",
                "county",
                "province",
            }:
                return False
        elif signal.signal_type in {"address", "poi", "street"}:
            if result_type in self.ADMINISTRATIVE_RESULT_TYPES:
                return False
            if result_type in self.CITY_RESULT_TYPES:
                return False
            if result_class in {"administrative", "boundary"}:
                return False
        elif signal.signal_type in {"region", "state", "province", "county"}:
            if result_type and result_type not in {
                "region",
                "state",
                "province",
                "county",
                "administrative",
            }:
                return False

        for context in context_signals:
            expected = self._normalize_text(
                context.normalized_value or context.raw_value
            )
            if not expected:
                continue
            if context.signal_type == "country":
                actual = self._normalize_text(
                    str(address.get("country") or address.get("country_name") or "")
                )
                code = self._normalize_text(str(address.get("country_code") or ""))
                if actual and not self._context_matches(actual, expected):
                    return False
                if not actual and not self._context_matches(display, expected):
                    return False
                if code and len(expected) == 2 and code != expected:
                    return False
            elif context.signal_type in {
                "city",
                "municipality",
                "neighborhood",
                "district",
            }:
                actual = self._normalize_text(
                    str(
                        address.get("city")
                        or address.get("town")
                        or address.get("village")
                        or address.get("municipality")
                        or ""
                    )
                )
                if actual and not self._context_matches(actual, expected):
                    return False
                if not actual and not self._context_matches(display, expected):
                    return False
            elif context.signal_type in {"region", "state", "province", "county"}:
                actual = self._normalize_text(
                    str(
                        address.get("state")
                        or address.get("region")
                        or address.get("province")
                        or address.get("county")
                        or ""
                    )
                )
                if actual and not self._context_matches(actual, expected):
                    return False
                if not actual and not self._context_matches(display, expected):
                    return False
        return True

    # -------------------------------------------------------------------------
    def _target_matches_candidate(
        self,
        candidate_text: str,
        target: str,
        signal_type: str,
    ) -> bool:
        """Match names while allowing a generic role word around the name.

        Geocoders commonly index a named facility as ``European Space Agency``
        while an extraction model describes it as ``European Space Agency
        site``.  The full target remains the first and preferred match; the
        reduced form is only allowed for specific named targets and never for
        a country, administrative parent, or acronym-only child feature.
        """

        if self._contains_location_text(candidate_text, target):
            return True
        if signal_type not in {"address", "poi", "street"}:
            return False
        target_tokens = re.findall(r"[a-z0-9]+", target.casefold())
        core_tokens = [
            token
            for token in target_tokens
            if token not in self.GENERIC_TARGET_DESCRIPTORS
        ]
        if not core_tokens:
            return False
        if self._contains_location_text(candidate_text, " ".join(core_tokens)):
            return True
        return False

    # -------------------------------------------------------------------------
    def _context_value(
        self, signals: Sequence[LocationSignal], signal_types: set[str]
    ) -> str | None:
        values = self._context_values(signals, signal_types)
        return values[0] if values else None

    # -------------------------------------------------------------------------
    def _context_values(
        self, signals: Sequence[LocationSignal], signal_types: set[str]
    ) -> list[str]:
        values: list[str] = []
        for signal in signals:
            if signal.signal_type not in signal_types:
                continue
            value = (signal.normalized_value or signal.raw_value).strip()
            if value and self._normalize_text(value) not in {
                self._normalize_text(item) for item in values
            }:
                values.append(value)
        return values

    # -------------------------------------------------------------------------
    def _address_component(self, candidate: dict[str, Any], *keys: str) -> str | None:
        address = json_object(candidate.get("address"))
        for key in keys:
            value = address.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    # -------------------------------------------------------------------------
    def _normalize_text(self, value: str) -> str:
        normalizer = getattr(self.nominatim_service, "normalize_component", None)
        if callable(normalizer):
            return str(normalizer(value))
        return " ".join(value.casefold().split())

    # -------------------------------------------------------------------------
    def _contains_location_text(self, haystack: str, needle: str) -> bool:
        def tokenize(value: str) -> list[str]:
            return re.findall(r"[a-z0-9]+", value.casefold())

        needle_tokens = tokenize(needle)
        haystack_tokens = tokenize(haystack)
        if not needle_tokens or not haystack_tokens:
            return False
        width = len(needle_tokens)
        if any(
            haystack_tokens[index : index + width] == needle_tokens
            for index in range(len(haystack_tokens) - width + 1)
        ):
            return True
        return all(token in set(haystack_tokens) for token in needle_tokens)

    # -------------------------------------------------------------------------
    def _context_matches(self, actual: str, expected: str) -> bool:
        """Match a geocoder component against a canonical parent signal.

        Extraction may normalize a parent signal to a hierarchical label such
        as Rome, Roma Capitale, Lazio, Italy while the geocoder returns only
        the locality component Rome. Accept either direction of token
        containment so a verified locality is not rejected merely because the
        two systems use different label granularity. Unrelated compounds
        still fail because neither complete token set contains the other.
        """

        return self._contains_location_text(
            actual, expected
        ) or self._contains_location_text(expected, actual)

    # -------------------------------------------------------------------------
    @classmethod
    def _location_from_memory(cls, active: dict[str, Any]) -> ResolvedLocation | None:
        if not active:
            return None
        latitude = cls._number(active.get("latitude"))
        longitude = cls._number(active.get("longitude"))
        label = str(active.get("label") or "").strip()
        if not label or not cls._valid_coordinates(latitude, longitude):
            return None
        try:
            return ResolvedLocation(
                label=label,
                latitude=latitude,
                longitude=longitude,
                country=active.get("country")
                if isinstance(active.get("country"), str)
                else None,
                city=active.get("city")
                if isinstance(active.get("city"), str)
                else None,
                address=active.get("address")
                if isinstance(active.get("address"), str)
                else None,
                source=str(active.get("source") or "memory"),
                confidence=cls._bounded_confidence(active.get("confidence"), 0.85),
                location_type=active.get("location_type")
                if isinstance(active.get("location_type"), str)
                else None,
                location_class=active.get("location_class")
                if isinstance(active.get("location_class"), str)
                else None,
                bbox=cls._valid_bbox(active.get("bbox")),
                bbox_source=active.get("bbox_source")
                if isinstance(active.get("bbox_source"), str)
                else None,
                provenance=cls._provenance_from_memory(active),
            )
        except (TypeError, ValueError):
            return None

    # -------------------------------------------------------------------------
    @staticmethod
    def _number(value: object) -> float | None:
        if isinstance(value, bool):
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) else None

    # -------------------------------------------------------------------------
    @staticmethod
    def _valid_coordinates(
        latitude: float | None, longitude: float | None
    ) -> bool:
        return (
            latitude is not None
            and longitude is not None
            and math.isfinite(latitude)
            and math.isfinite(longitude)
            and -90.0 <= latitude <= 90.0
            and -180.0 <= longitude <= 180.0
        )

    # -------------------------------------------------------------------------
    @classmethod
    def _valid_bbox(cls, value: object) -> list[float] | None:
        if not isinstance(value, (list, tuple)) or len(value) != 4:
            return None
        numbers = [cls._number(item) for item in value]
        if any(item is None for item in numbers):
            return None
        west, south, east, north = numbers
        assert west is not None and south is not None
        assert east is not None and north is not None
        if not (-180 <= west <= 180 and -180 <= east <= 180):
            return None
        if not (-90 <= south <= 90 and -90 <= north <= 90):
            return None
        if west > east or south > north:
            return None
        return [west, south, east, north]

    # -------------------------------------------------------------------------
    @classmethod
    def _bounded_confidence(cls, value: object, fallback: float) -> float:
        number = cls._number(value)
        if number is None:
            number = fallback
        return max(0.0, min(1.0, number))

    # -------------------------------------------------------------------------
    @staticmethod
    def _provenance_from_geocoded(
        value: dict[str, Any],
    ) -> LocationResolutionProvenance | None:
        provider = str(value.get("provider") or "").strip()
        fetched_at = value.get("fetched_at")
        if not provider or fetched_at is None:
            return None
        try:
            return LocationResolutionProvenance.model_validate(
                {
                    "provider": provider,
                    "source_url": value.get("source_url"),
                    "fetched_at": fetched_at,
                    "result_status": value.get("result_status") or "ok",
                    "result_type": value.get("result_type") or "location",
                }
            )
        except (TypeError, ValueError):
            return None

    # -------------------------------------------------------------------------
    @staticmethod
    def _provenance_from_memory(
        value: dict[str, Any],
    ) -> LocationResolutionProvenance | None:
        raw = value.get("provenance")
        if not isinstance(raw, dict):
            return None
        try:
            return LocationResolutionProvenance.model_validate(raw)
        except (TypeError, ValueError):
            return None

    # -------------------------------------------------------------------------
    def build_ambiguity_question(
        self,
        candidates: Sequence[LocationSignal],
        *,
        reason: str = "Multiple location signals have similar confidence.",
    ) -> ClarificationRequest:
        options: list[str] = []
        for candidate in candidates:
            label = str(candidate.normalized_value or candidate.raw_value or "").strip()
            if label and label not in options:
                options.append(label)
        return ClarificationRequest(
            question=f"Which location do you mean: {', '.join(options)}?",
            reason=reason,
            missing_fields=["location"],
        )
