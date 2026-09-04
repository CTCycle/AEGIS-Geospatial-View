from __future__ import annotations

import math
import re
from typing import Any, cast

from server.common.typing import json_object

from typing import Sequence

from server.common.logger import logger as LOGGER
from server.domain.agent.decision import (
    ClarificationRequest,
    LocationHierarchy,
    LocationHierarchyEntry,
    LocationResolutionProvenance,
    ResolvedLocation,
)
from server.contracts.extraction import LocationSignal
from server.services.geospatial.nominatim import NominatimService


###############################################################################
class LocationResolver:
    SPECIFICITY_BY_SIGNAL_TYPE = {
        "coordinates": 6,
        "address": 5,
        "poi": 5,
        "street": 5,
        "neighborhood": 4,
        "district": 4,
        "municipality": 3,
        "city": 3,
        "county": 2,
        "province": 2,
        "state": 2,
        "region": 2,
        "country": 1,
        "deictic": 0,
    }
    MAX_RELATIONSHIP_PROBES = 3
    DEICTIC_SIGNAL_TYPES = frozenset({"deictic"})
    DISTRICT_RESULT_TYPES = frozenset(
        {
            "neighbourhood",
            "neighborhood",
            "suburb",
            "quarter",
            "city_district",
            "district",
            "borough",
            "locality",
        }
    )
    DISTRICT_ADDRESS_TYPES = frozenset(
        {
            "neighbourhood",
            "neighborhood",
            "suburb",
            "quarter",
            "city_district",
            "district",
            "borough",
            "locality",
        }
    )
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
    COUNTRY_ALIASES: dict[str, frozenset[str]] = {
        "united kingdom": frozenset({"uk", "u k", "gb", "great britain", "britain"}),
        "united states": frozenset({"us", "u s", "usa", "america"}),
        "italy": frozenset({"italia", "italie", "it"}),
        "germany": frozenset({"deutschland", "allemagne", "de"}),
        "france": frozenset({"fr", "republique francaise"}),
        "spain": frozenset({"espana", "españa", "es"}),
        "netherlands": frozenset({"holland", "nederland", "nl"}),
        "australia": frozenset({"au"}),
        "canada": frozenset({"ca"}),
    }

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

        # A deictic expression such as "there" points at conversation state; it
        # is never a competing geographic target when an explicit place is
        # present.  If it is the only signal, reuse the active resolved object
        # instead of sending the pronoun to the geocoder.
        explicit_signals = [
            signal
            for signal in location_signals
            if signal.signal_type not in {"coordinates", *self.DEICTIC_SIGNAL_TYPES}
            and signal.raw_value.strip()
        ]
        if not explicit_signals:
            active = json_object(memory_snapshot.get("active_location"))
            remembered = self._location_from_memory(active)
            if remembered is not None:
                return remembered
            return ClarificationRequest(
                question="I could not resolve that location. Can you provide a city or coordinates?",
                reason="Only a contextual location reference was provided and no valid active location exists.",
                missing_fields=["location"],
            )

        context_signals = [
            *explicit_signals,
            *self._memory_parent_signals(memory_snapshot, explicit_signals),
        ]
        highest_specificity = max(
            self.SPECIFICITY_BY_SIGNAL_TYPE.get(signal.signal_type, 0)
            for signal in context_signals
        )
        target_signals = [
            signal
            for signal in context_signals
            if self.SPECIFICITY_BY_SIGNAL_TYPE.get(signal.signal_type, 0)
            == highest_specificity
        ]
        target_signals = self._dedupe_signals(target_signals)
        if len(target_signals) > 1:
            related = await self._resolve_same_level_relationship(target_signals)
            if related is not None:
                return related
            return self.build_ambiguity_question(
                target_signals,
                reason="Multiple same-level location targets were provided.",
            )

        target = target_signals[0]
        parent_signals = [signal for signal in context_signals if signal is not target]
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
    async def _resolve_same_level_relationship(
        self, signals: Sequence[LocationSignal]
    ) -> ResolvedLocation | ClarificationRequest | None:
        """Try a bounded parent/child interpretation for model-level conflicts.

        Correctly typed signals never reach this method for normal hierarchy
        requests.  It exists for model output such as ``EUR, Rome`` where both
        entities were labelled as cities.  Text-authored/unit-test conflicts
        remain ambiguous without evidence; a production parser signal is
        probed at most three times and only one surviving candidate is accepted.
        """

        candidates = list(signals)[: self.MAX_RELATIONSHIP_PROBES]
        if len(candidates) < 2 or not any(item.source == "model" for item in candidates):
            return None
        resolved: list[ResolvedLocation] = []
        for candidate in candidates:
            context = [item for item in candidates if item is not candidate]
            result = await self._resolve_signal(
                candidate,
                context_signals=context,
                allow_related_type=True,
            )
            if isinstance(result, ResolvedLocation):
                resolved.append(result)
        if len(resolved) == 1:
            return resolved[0]
        if len(resolved) > 1:
            first = resolved[0]
            if all(self._same_resolved_location(first, item) for item in resolved[1:]):
                return first
        return None

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
    def _memory_parent_signals(
        self,
        memory_snapshot: dict[str, Any],
        explicit_signals: Sequence[LocationSignal],
    ) -> list[LocationSignal]:
        """Use the active resolved place only as context for a finer target."""

        active = json_object(memory_snapshot.get("active_location"))
        if not active:
            return []
        active_type = self._normalize_text(str(active.get("location_type") or ""))
        active_specificity = self.SPECIFICITY_BY_SIGNAL_TYPE.get(active_type, 0)
        target_specificity = max(
            self.SPECIFICITY_BY_SIGNAL_TYPE.get(signal.signal_type, 0)
            for signal in explicit_signals
        )
        if target_specificity <= active_specificity:
            return []

        explicit_types = {signal.signal_type for signal in explicit_signals}
        inherited: list[LocationSignal] = []
        active_city = str(active.get("city") or "").strip()
        active_country = str(active.get("country") or "").strip()
        target_is_finer_place = target_specificity >= self.SPECIFICITY_BY_SIGNAL_TYPE[
            "neighborhood"
        ]
        if (
            target_is_finer_place
            and active_city
            and not explicit_types.intersection(
                {"city", "municipality", "town", "village"}
            )
        ):
            inherited.append(
                LocationSignal(
                    signal_type="city",
                    raw_value=active_city,
                    normalized_value=active_city,
                    confidence=self._bounded_confidence(
                        active.get("confidence"), 0.85
                    ),
                    source="memory",
                )
            )
        inherited_city = any(signal.signal_type == "city" for signal in inherited)
        if (
            inherited_city
            and active_country
            and "country" not in explicit_types
        ):
            inherited.append(
                LocationSignal(
                    signal_type="country",
                    raw_value=active_country,
                    normalized_value=active_country,
                    confidence=self._bounded_confidence(
                        active.get("confidence"), 0.85
                    ),
                    source="memory",
                )
            )
        return inherited

    # -------------------------------------------------------------------------
    def _has_conflicting_parent_signals(
        self, signals: Sequence[LocationSignal]
    ) -> bool:
        by_specificity: dict[int, set[str]] = {}
        for signal in signals:
            specificity = self.SPECIFICITY_BY_SIGNAL_TYPE.get(signal.signal_type, 0)
            value = self._canonical_context_value(
                signal.signal_type,
                signal.normalized_value or signal.raw_value,
            )
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
        allow_related_type: bool = False,
    ) -> ResolvedLocation | ClarificationRequest | None:
        signal_latitude = signal.latitude
        signal_longitude = signal.longitude
        # Coordinates attached to a named entity by the parser are only a
        # model hint. The explicit ``coordinates`` signal is the only form
        # that can bypass geocoding; otherwise we would accept an unverified
        # point and lose the entity's parent hierarchy (for example, EUR in
        # Rome).
        if signal.signal_type == "coordinates" and self._valid_coordinates(
            signal_latitude, signal_longitude
        ):
            assert signal_latitude is not None and signal_longitude is not None
            return ResolvedLocation(
                label=signal.raw_value or signal.normalized_value or "Coordinates",
                latitude=float(signal_latitude),
                longitude=float(signal_longitude),
                source=signal.source,
                confidence=signal.confidence,
                location_type=signal.signal_type,
                hierarchy=LocationHierarchy(
                    target=self._hierarchy_entry(signal),
                    parents=[],
                ),
            )
        raw_target = signal.raw_value.strip() or (signal.normalized_value or "").strip()
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
        expected_location_type = None if allow_related_type else signal.signal_type
        geocoded = await self.nominatim_service.extract_coordinates(
            address=address,
            city=(
                city
                if signal.signal_type
                in {"address", "poi", "street", "neighborhood", "district"}
                or (allow_related_type and city)
                else None
            ),
            country_name=country,
            country_code=None,
            expected_location_type=expected_location_type,
        )
        geocoded = json_object(geocoded)
        if not geocoded:
            return None
        ambiguous_candidates = geocoded.get("ambiguous_candidates")
        if isinstance(ambiguous_candidates, list):
            options = [
                str(json_object(item).get("display_name") or "").strip()
                for item in cast(list[object], ambiguous_candidates)
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
            allow_related_type=allow_related_type,
        ):
            LOGGER.warning(
                "Rejecting geocoder candidate that does not match target=%s type=%s display=%s",
                raw_target,
                geocoded.get("selected_result_type"),
                geocoded.get("display_name"),
            )
            return None
        latitude = self._number(geocoded.get("lat"))
        longitude = self._number(geocoded.get("lon"))
        if not self._valid_coordinates(latitude, longitude):
            return None
        assert latitude is not None and longitude is not None
        bbox = self._valid_bbox(geocoded.get("bbox"))
        geocoder_type = self._normalize_text(
            str(geocoded.get("selected_result_type") or "")
        )
        resolved_type = geocoder_type or None
        if signal.signal_type in {"district", "neighborhood"} and (
            geocoder_type in self.DISTRICT_RESULT_TYPES
            or self._normalize_text(
                str(geocoded.get("selected_address_type") or "")
            )
            in self.DISTRICT_ADDRESS_TYPES
        ):
            resolved_type = signal.signal_type
        elif allow_related_type and (
            geocoder_type in self.DISTRICT_RESULT_TYPES
            or self._normalize_text(
                str(geocoded.get("selected_address_type") or "")
            )
            in self.DISTRICT_ADDRESS_TYPES
        ):
            resolved_type = "district"
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
        hierarchy = self._build_hierarchy(
            signal=signal,
            context_signals=context_signals,
            geocoded=geocoded,
        )
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
                hierarchy=hierarchy,
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
        allow_related_type: bool = False,
    ) -> bool:
        # Keep the extracted span for validation.  Canonical model text is
        # used only to form the geocoder query in _resolve_signal; this avoids
        # accepting a candidate solely because a model rewrote its parentage.
        target = self._normalize_text(signal.raw_value or signal.normalized_value or "")
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
            allow_related_type=allow_related_type,
        ):
            return False

        result_type = self._normalize_text(str(candidate.get("selected_result_type") or ""))
        result_class = self._normalize_text(str(candidate.get("selected_result_class") or ""))
        address_type = self._normalize_text(
            str(candidate.get("selected_address_type") or "")
        )
        if allow_related_type:
            # A same-level probe is deliberately permissive about result type;
            # the target text and parent components still have to match.  This
            # is what lets a model-labelled city be discovered as a district.
            pass
        elif signal.signal_type == "country":
            if result_type and result_type != "country":
                return False
        elif signal.signal_type in {"city", "municipality"}:
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
        elif signal.signal_type in {"neighborhood", "district"}:
            if not self._is_district_candidate(
                candidate,
                target=target,
                candidate_text=candidate_text,
            ):
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
                if actual and not self._context_matches(actual, expected, country=True):
                    return False
                if not actual and not self._context_matches(display, expected, country=True):
                    return False
                if code and not self._country_codes(expected).intersection({code}):
                    return False
            elif context.signal_type in {"neighborhood", "district"}:
                actual = self._normalize_text(
                    str(
                        next(
                            (
                                address.get(key)
                                for key in (
                                    "neighbourhood",
                                    "neighborhood",
                                    "suburb",
                                    "quarter",
                                    "city_district",
                                    "district",
                                    "borough",
                                    "locality",
                                )
                                if address.get(key)
                            ),
                            "",
                        )
                    )
                )
                if actual and not self._context_matches(actual, expected):
                    return False
                if not actual and not self._context_matches(display, expected):
                    return False
            elif context.signal_type in {"city", "municipality"}:
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
        *,
        allow_related_type: bool = False,
    ) -> bool:
        """Match names while allowing a generic role word around the name.

        Geocoders commonly index a named facility as ``European Space Agency``
        while an extraction model describes it as ``European Space Agency
        site``.  The full target remains the first and preferred match; the
        reduced form is only allowed for specific named targets and never for
        a country, administrative parent, or acronym-only child feature.
        """

        if signal_type == "country" and any(
            self._contains_location_text(candidate_text, alias)
            for alias in self._country_aliases(target)
        ):
            return True
        if self._contains_location_text(candidate_text, target):
            return True
        target_without_country = self._strip_country_suffix(target)
        if target_without_country and self._contains_location_text(
            candidate_text, target_without_country
        ):
            return True
        if signal_type not in {
            "address",
            "poi",
            "street",
            "neighborhood",
            "district",
        } and not allow_related_type:
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
    def _is_district_candidate(
        self,
        candidate: dict[str, Any],
        *,
        target: str,
        candidate_text: str,
    ) -> bool:
        result_type = self._normalize_text(
            str(candidate.get("selected_result_type") or "")
        )
        address_type = self._normalize_text(
            str(candidate.get("selected_address_type") or "")
        )
        address = json_object(candidate.get("address"))
        has_named_child = any(
            self._contains_location_text(
                self._normalize_text(str(address.get(key) or "")), target
            )
            for key in (
                "neighbourhood",
                "neighborhood",
                "suburb",
                "quarter",
                "city_district",
                "district",
                "borough",
                "locality",
            )
        )
        if result_type in self.DISTRICT_RESULT_TYPES or address_type in self.DISTRICT_ADDRESS_TYPES:
            return True
        if has_named_child:
            return result_type in {"administrative", "boundary"}
        # Boundary responses can still be valid when Nominatim omitted the
        # granular address key but retained the named district in the display
        # name.  Do not accept a plain city/country parent as a district.
        return result_type in {"administrative", "boundary"} and self._contains_location_text(
            candidate_text, target
        )

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
    def _canonical_context_value(self, signal_type: str, value: str) -> str:
        normalized = self._normalize_text(value)
        if signal_type != "country":
            return normalized
        aliases = self._country_aliases(normalized)
        return sorted(aliases)[0] if aliases else normalized

    # -------------------------------------------------------------------------
    def _strip_country_suffix(self, value: str) -> str:
        normalized = self._normalize_text(value)
        if not normalized:
            return ""
        aliases = {
            self._normalize_text(alias)
            for canonical, values in self.COUNTRY_ALIASES.items()
            for alias in (canonical, *values)
        }
        for alias in sorted(aliases, key=len, reverse=True):
            if normalized == alias:
                return ""
            suffix = f" {alias}"
            if normalized.endswith(suffix):
                return normalized[: -len(suffix)].strip()
        return normalized

    # -------------------------------------------------------------------------
    def _country_aliases(self, value: str) -> set[str]:
        normalized = self._normalize_text(value)
        for canonical, aliases in self.COUNTRY_ALIASES.items():
            normalized_aliases = {
                self._normalize_text(canonical),
                *(self._normalize_text(alias) for alias in aliases),
            }
            if normalized in normalized_aliases:
                return normalized_aliases
        return {normalized} if normalized else set()

    # -------------------------------------------------------------------------
    def _country_codes(self, value: str) -> set[str]:
        normalized = self._normalize_text(value)
        codes = {
            "united kingdom": "gb",
            "uk": "gb",
            "great britain": "gb",
            "united states": "us",
            "usa": "us",
            "italy": "it",
            "italia": "it",
            "germany": "de",
            "deutschland": "de",
            "france": "fr",
            "spain": "es",
            "espana": "es",
            "españa": "es",
            "netherlands": "nl",
            "holland": "nl",
            "australia": "au",
            "canada": "ca",
        }
        values = self._country_aliases(normalized) or {normalized}
        return {
            codes.get(item, item)
            for item in values
            if item
        }

    # -------------------------------------------------------------------------
    def _hierarchy_entry(
        self,
        signal: LocationSignal,
        *,
        canonical_label: str | None = None,
        signal_type: str | None = None,
        source: str | None = None,
    ) -> LocationHierarchyEntry:
        return LocationHierarchyEntry(
            signal_type=signal_type or signal.signal_type,
            raw_value=signal.raw_value,
            normalized_value=signal.normalized_value or signal.raw_value,
            confidence=self._bounded_confidence(signal.confidence, 0.0),
            source=source or signal.source,
            canonical_label=canonical_label,
        )

    # -------------------------------------------------------------------------
    def _build_hierarchy(
        self,
        *,
        signal: LocationSignal,
        context_signals: Sequence[LocationSignal],
        geocoded: dict[str, Any],
    ) -> LocationHierarchy:
        hierarchy_signal_type = signal.signal_type
        geocoder_type = self._normalize_text(
            str(geocoded.get("selected_result_type") or "")
        )
        geocoder_address_type = self._normalize_text(
            str(geocoded.get("selected_address_type") or "")
        )
        if signal.signal_type in {"city", "municipality"} and (
            geocoder_type in self.DISTRICT_RESULT_TYPES
            or geocoder_address_type in self.DISTRICT_ADDRESS_TYPES
        ):
            hierarchy_signal_type = "district"
        target = self._hierarchy_entry(
            signal,
            canonical_label=str(geocoded.get("display_name") or "").strip()
            or None,
            # Keep the user's semantic granularity in the hierarchy even
            # when the provider uses a related result type such as ``suburb``
            # for a district/neighborhood.
            signal_type=hierarchy_signal_type,
        )
        parents: list[LocationHierarchyEntry] = []
        seen: set[tuple[str, str]] = set()
        for parent in sorted(
            (item for item in context_signals if item.signal_type not in self.DEICTIC_SIGNAL_TYPES),
            key=lambda item: self.SPECIFICITY_BY_SIGNAL_TYPE.get(item.signal_type, 0),
            reverse=True,
        ):
            value = parent.normalized_value or parent.raw_value
            key = (parent.signal_type, self._canonical_context_value(parent.signal_type, value))
            if not key[1] or key in seen:
                continue
            seen.add(key)
            parents.append(
                self._hierarchy_entry(
                    parent,
                    canonical_label=self._geocoder_parent_label(geocoded, parent.signal_type)
                    or value,
                )
            )

        inferred = (
            ("city", self._address_component(geocoded, "city", "town", "village", "municipality")),
            ("region", self._address_component(geocoded, "state", "region", "province", "county")),
            ("country", self._address_component(geocoded, "country")),
        )
        for parent_type, label in inferred:
            if not label or parent_type == target.signal_type:
                continue
            key = (parent_type, self._canonical_context_value(parent_type, label))
            if not key[1] or key in seen:
                continue
            seen.add(key)
            parents.append(
                LocationHierarchyEntry(
                    signal_type=parent_type,
                    raw_value=label,
                    normalized_value=label,
                    confidence=target.confidence,
                    source="geocoder",
                    canonical_label=label,
                )
            )
        parents.sort(
            key=lambda item: self.SPECIFICITY_BY_SIGNAL_TYPE.get(item.signal_type, 0),
            reverse=True,
        )
        return LocationHierarchy(target=target, parents=parents)

    # -------------------------------------------------------------------------
    def _geocoder_parent_label(
        self, geocoded: dict[str, Any], signal_type: str
    ) -> str | None:
        if signal_type == "country":
            return self._address_component(geocoded, "country")
        if signal_type in {"city", "municipality"}:
            return self._address_component(
                geocoded, "city", "town", "village", "municipality"
            )
        if signal_type in {"neighborhood", "district"}:
            return self._address_component(
                geocoded,
                "neighbourhood",
                "neighborhood",
                "suburb",
                "quarter",
                "city_district",
                "district",
                "borough",
                "locality",
            )
        if signal_type in {"region", "state", "province", "county"}:
            return self._address_component(
                geocoded, "state", "region", "province", "county"
            )
        return None

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
    def _context_matches(
        self, actual: str, expected: str, *, country: bool = False
    ) -> bool:
        """Match a geocoder component against a canonical parent signal.

        Extraction may normalize a parent signal to a hierarchical label such
        as Rome, Roma Capitale, Lazio, Italy while the geocoder returns only
        the locality component Rome. Accept either direction of token
        containment so a verified locality is not rejected merely because the
        two systems use different label granularity. Unrelated compounds
        still fail because neither complete token set contains the other.
        """

        if country and self._country_aliases(actual).intersection(
            self._country_aliases(expected)
        ):
            return True
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
        assert latitude is not None and longitude is not None
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
                hierarchy=(
                    LocationHierarchy.model_validate(active.get("hierarchy"))
                    if isinstance(active.get("hierarchy"), dict)
                    else None
                ),
            )
        except (TypeError, ValueError):
            return None

    # -------------------------------------------------------------------------
    @staticmethod
    def _number(value: object) -> float | None:
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
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
        if not isinstance(value, (list, tuple)):
            return None
        values = cast(list[object] | tuple[object, ...], value)
        if len(values) != 4:
            return None
        numbers = [cls._number(item) for item in values]
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
