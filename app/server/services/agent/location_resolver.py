from __future__ import annotations

from typing import Any

from server.common.typing import json_array, json_object

from typing import Sequence

from server.common.logger import logger as LOGGER
from server.domain.agent.decision import ClarificationRequest, ResolvedLocation
from server.contracts.extraction import LocationSignal
from server.services.geospatial.nominatim import NominatimService

###############################################################################
class LocationResolver:
    SPECIFICITY_BY_SIGNAL_TYPE = {
        "coordinates": 4,
        "address": 3,
        "city": 2,
        "deictic": 2,
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
            if active:
                return ResolvedLocation(
                    label=str(active.get("label") or ""),
                    latitude=float(active.get("latitude") or 0.0),
                    longitude=float(active.get("longitude") or 0.0),
                    country=active.get("country") if isinstance(active.get("country"), str) else None,
                    city=active.get("city") if isinstance(active.get("city"), str) else None,
                    address=active.get("address") if isinstance(active.get("address"), str) else None,
                    source=str(active.get("source") or "memory"),
                    confidence=float(active.get("confidence") or 0.85),
                    location_type=active.get("location_type") if isinstance(active.get("location_type"), str) else None,
                    location_class=active.get("location_class") if isinstance(active.get("location_class"), str) else None,
                    bbox=json_array(active.get("bbox")) or None,
                    bbox_source=active.get("bbox_source") if isinstance(active.get("bbox_source"), str) else None,
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
            and abs(resolved_candidates[0].confidence - resolved_candidates[1].confidence) < 0.12
            and self._specificity_gap_is_small(ranked_candidates[0], ranked_candidates[1])
            and not self._same_resolved_location(resolved_candidates[0], resolved_candidates[1])
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
    def score_location_matches(self, location_signals: Sequence[LocationSignal]) -> list[LocationSignal]:
        return sorted(
            location_signals,
            key=lambda item: (
                item.confidence,
                self.SPECIFICITY_BY_SIGNAL_TYPE.get(item.signal_type, 0),
            ),
            reverse=True,
        )

    # -------------------------------------------------------------------------
    def _specificity_gap_is_small(self, left: LocationSignal, right: LocationSignal) -> bool:
        left_specificity = self.SPECIFICITY_BY_SIGNAL_TYPE.get(left.signal_type, 0)
        right_specificity = self.SPECIFICITY_BY_SIGNAL_TYPE.get(right.signal_type, 0)
        return left_specificity == right_specificity

    # -------------------------------------------------------------------------
    def _same_resolved_point(self, left: LocationSignal, right: LocationSignal) -> bool:
        if any(value is None for value in (left.latitude, left.longitude, right.latitude, right.longitude)):
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
    def _same_resolved_location(self, left: ResolvedLocation, right: ResolvedLocation) -> bool:
        return (
            abs(float(left.latitude) - float(right.latitude)) < 0.01
            and abs(float(left.longitude) - float(right.longitude)) < 0.01
        )

    # -------------------------------------------------------------------------
    async def _resolve_signal(self, signal: LocationSignal) -> ResolvedLocation | None:
        if signal.latitude is not None and signal.longitude is not None:
            return ResolvedLocation(
                label=signal.normalized_value or signal.raw_value,
                latitude=signal.latitude,
                longitude=signal.longitude,
                source=signal.source,
                confidence=signal.confidence,
                location_type=signal.signal_type,
            )
        geocoded = await self.nominatim_service.extract_coordinates(
            address=signal.normalized_value or signal.raw_value,
            city=None,
            country_name=None,
            country_code=None,
        )
        geocoded = json_object(geocoded)
        if not geocoded:
            return None
        return ResolvedLocation(
            label=str(geocoded.get("display_name") or signal.raw_value),
            latitude=float(geocoded["lat"]),
            longitude=float(geocoded["lon"]),
            source="geocoder",
            confidence=float(geocoded.get("confidence") or signal.confidence),
            location_type=str(geocoded.get("selected_result_type") or "") or None,
            location_class=str(geocoded.get("selected_result_class") or "") or None,
            bbox=json_array(geocoded.get("bbox")) or None,
            bbox_source=str(geocoded.get("bbox_source") or "") or None,
        )

    # -------------------------------------------------------------------------
    def build_ambiguity_question(self, candidates: Sequence[LocationSignal]) -> ClarificationRequest:
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
