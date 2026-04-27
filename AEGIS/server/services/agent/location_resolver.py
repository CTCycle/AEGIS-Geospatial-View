from __future__ import annotations

from typing import Sequence

from AEGIS.server.domain.agent.decision import ClarificationRequest, ResolvedLocation
from AEGIS.server.domain.extraction.models import LocationSignal
from AEGIS.server.services.geospatial.nominatim import NominatimService

###############################################################################
class LocationResolver:
    def __init__(self, *, nominatim_service: NominatimService | None = None) -> None:
        self.nominatim_service = nominatim_service or NominatimService()

    async def resolve_location_signals(
        self,
        location_signals: list[LocationSignal],
        memory_snapshot: dict,
    ) -> ResolvedLocation | ClarificationRequest:
        if not location_signals:
            active = memory_snapshot.get("active_location") if isinstance(memory_snapshot, dict) else None
            if isinstance(active, dict):
                return ResolvedLocation(
                    label=str(active.get("label") or ""),
                    latitude=float(active.get("latitude")),
                    longitude=float(active.get("longitude")),
                    country=active.get("country") if isinstance(active.get("country"), str) else None,
                    city=active.get("city") if isinstance(active.get("city"), str) else None,
                    address=active.get("address") if isinstance(active.get("address"), str) else None,
                    source=str(active.get("source") or "memory"),
                    confidence=float(active.get("confidence") or 0.85),
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
            and not self._same_resolved_location(resolved_candidates[0], resolved_candidates[1])
        ):
            return self.build_ambiguity_question(ranked_candidates[:2])

        return resolved_candidates[0]

    def score_location_matches(self, location_signals: Sequence[LocationSignal]) -> list[LocationSignal]:
        return sorted(location_signals, key=lambda item: item.confidence, reverse=True)

    def _same_resolved_point(self, left: LocationSignal, right: LocationSignal) -> bool:
        if None in {left.latitude, left.longitude, right.latitude, right.longitude}:
            return False
        return (
            abs(float(left.latitude) - float(right.latitude)) < 0.01
            and abs(float(left.longitude) - float(right.longitude)) < 0.01
        )

    def _same_resolved_location(self, left: ResolvedLocation, right: ResolvedLocation) -> bool:
        return (
            abs(float(left.latitude) - float(right.latitude)) < 0.01
            and abs(float(left.longitude) - float(right.longitude)) < 0.01
        )

    async def _resolve_signal(self, signal: LocationSignal) -> ResolvedLocation | None:
        if signal.latitude is not None and signal.longitude is not None:
            return ResolvedLocation(
                label=signal.normalized_value or signal.raw_value,
                latitude=signal.latitude,
                longitude=signal.longitude,
                source=signal.source,
                confidence=signal.confidence,
            )
        geocoded = await self.nominatim_service.extract_coordinates(
            address=signal.normalized_value or signal.raw_value,
            city=None,
            country_name=None,
            country_code=None,
        )
        if not isinstance(geocoded, dict):
            return None
        return ResolvedLocation(
            label=str(geocoded.get("display_name") or signal.raw_value),
            latitude=float(geocoded["lat"]),
            longitude=float(geocoded["lon"]),
            source="geocoder",
            confidence=float(geocoded.get("confidence") or signal.confidence),
        )

    def build_ambiguity_question(self, candidates: Sequence[LocationSignal]) -> ClarificationRequest:
        options = ", ".join((candidate.raw_value for candidate in candidates if candidate.raw_value))
        return ClarificationRequest(
            question=f"I found multiple possible locations: {options}. Which one should I use?",
            reason="Multiple location signals have similar confidence.",
            missing_fields=["location"],
        )
