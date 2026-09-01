from __future__ import annotations

import math
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

        ranked = self.score_location_matches(location_signals)
        resolved_candidates: list[ResolvedLocation] = []
        ranked_candidates: list[LocationSignal] = []
        for signal in ranked[:3]:
            resolved = await self._resolve_signal(signal)
            if resolved is None:
                continue
            resolved_candidates.append(resolved)
            ranked_candidates.append(signal)

        if not resolved_candidates:
            return ClarificationRequest(
                question="I could not resolve that location. Can you provide a city or coordinates?",
                reason="Geocoder did not return a valid candidate.",
                missing_fields=["location"],
            )

        if (
            len(resolved_candidates) > 1
            and abs(
                resolved_candidates[0].confidence - resolved_candidates[1].confidence
            )
            < 0.12
            and self._specificity_gap_is_small(
                ranked_candidates[0], ranked_candidates[1]
            )
            and not self._same_resolved_location(
                resolved_candidates[0], resolved_candidates[1]
            )
        ):
            return self.build_ambiguity_question(ranked_candidates[:2])

        LOGGER.info(
            "location_resolved label=%s source=%s confidence=%.3f type=%s class=%s bbox=%s",
            resolved_candidates[0].label,
            resolved_candidates[0].source,
            resolved_candidates[0].confidence,
            resolved_candidates[0].location_type,
            resolved_candidates[0].location_class,
            resolved_candidates[0].bbox,
        )
        return resolved_candidates[0]

    # -------------------------------------------------------------------------
    def score_location_matches(
        self, location_signals: Sequence[LocationSignal]
    ) -> list[LocationSignal]:
        return sorted(
            location_signals,
            key=lambda item: (
                item.confidence,
                self.SPECIFICITY_BY_SIGNAL_TYPE.get(item.signal_type, 0),
            ),
            reverse=True,
        )

    # -------------------------------------------------------------------------
    def _specificity_gap_is_small(
        self, left: LocationSignal, right: LocationSignal
    ) -> bool:
        left_specificity = self.SPECIFICITY_BY_SIGNAL_TYPE.get(left.signal_type, 0)
        right_specificity = self.SPECIFICITY_BY_SIGNAL_TYPE.get(right.signal_type, 0)
        return left_specificity == right_specificity

    # -------------------------------------------------------------------------
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
    async def _resolve_signal(self, signal: LocationSignal) -> ResolvedLocation | None:
        if self._valid_coordinates(signal.latitude, signal.longitude):
            return ResolvedLocation(
                label=signal.normalized_value or signal.raw_value,
                latitude=float(signal.latitude),
                longitude=float(signal.longitude),
                source=signal.source,
                confidence=signal.confidence,
                location_type=signal.signal_type,
            )
        geocoded = await self.nominatim_service.extract_coordinates(
            address=signal.normalized_value or signal.raw_value,
            city=(signal.normalized_value or signal.raw_value)
            if signal.signal_type in {"city", "municipality"}
            else None,
            country_name=(signal.normalized_value or signal.raw_value)
            if signal.signal_type == "country"
            else None,
            country_code=None,
            expected_location_type=signal.signal_type,
        )
        geocoded = json_object(geocoded)
        if not geocoded:
            return None
        latitude = self._number(geocoded.get("lat"))
        longitude = self._number(geocoded.get("lon"))
        if not self._valid_coordinates(latitude, longitude):
            return None
        bbox = self._valid_bbox(geocoded.get("bbox"))
        try:
            return ResolvedLocation(
                label=str(geocoded.get("display_name") or signal.raw_value),
                latitude=latitude,
                longitude=longitude,
                source="geocoder",
                confidence=self._bounded_confidence(
                    geocoded.get("confidence"), signal.confidence
                ),
                location_type=str(geocoded.get("selected_result_type") or "")
                or None,
                location_class=str(geocoded.get("selected_result_class") or "")
                or None,
                bbox=bbox,
                bbox_source=str(geocoded.get("bbox_source") or "") or None,
                provenance=self._provenance_from_geocoded(geocoded),
            )
        except (TypeError, ValueError):
            return None

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
        self, candidates: Sequence[LocationSignal]
    ) -> ClarificationRequest:
        options: list[str] = []
        for candidate in candidates:
            label = str(candidate.normalized_value or candidate.raw_value or "").strip()
            if label and label not in options:
                options.append(label)
        return ClarificationRequest(
            question=f"Which location do you mean: {', '.join(options)}?",
            reason="Multiple location signals have similar confidence.",
            missing_fields=["location"],
        )
