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
                return ResolvedLocation.model_validate(active)
            return ClarificationRequest(
                question="Which location should I use?",
                reason="No resolvable location signal found.",
                missing_fields=["location"],
            )

        ranked = self.score_location_matches(location_signals)
        top = ranked[0]
        if len(ranked) > 1 and abs(ranked[0].confidence - ranked[1].confidence) < 0.12:
            return self.build_ambiguity_question(ranked[:2])

        if top.signal_type == "coordinates" and top.latitude is not None and top.longitude is not None:
            return ResolvedLocation(
                label=top.normalized_value or top.raw_value,
                latitude=top.latitude,
                longitude=top.longitude,
                source=top.source,
                confidence=top.confidence,
            )

        geocoded = await self.nominatim_service.extract_coordinates(
            address=top.normalized_value or top.raw_value,
            city=None,
            country_name=None,
            country_code=None,
        )
        if not isinstance(geocoded, dict):
            return ClarificationRequest(
                question="I could not resolve that location. Can you provide a city or coordinates?",
                reason="Geocoder did not return a valid candidate.",
                missing_fields=["location"],
            )

        return ResolvedLocation(
            label=str(geocoded.get("display_name") or top.raw_value),
            latitude=float(geocoded["lat"]),
            longitude=float(geocoded["lon"]),
            source="geocoder",
            confidence=float(geocoded.get("confidence") or top.confidence),
        )

    def score_location_matches(self, location_signals: Sequence[LocationSignal]) -> list[LocationSignal]:
        return sorted(location_signals, key=lambda item: item.confidence, reverse=True)

    def build_ambiguity_question(self, candidates: Sequence[LocationSignal]) -> ClarificationRequest:
        options = ", ".join((candidate.raw_value for candidate in candidates if candidate.raw_value))
        return ClarificationRequest(
            question=f"I found multiple possible locations: {options}. Which one should I use?",
            reason="Multiple location signals have similar confidence.",
            missing_fields=["location"],
        )
