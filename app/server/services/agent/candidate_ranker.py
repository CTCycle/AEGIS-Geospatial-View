from __future__ import annotations

from server.domain.agent.decision import CapabilityCandidate, ResolvedLocation
from server.domain.extraction.models import TurnParseResult
from server.services.geospatial.coverage import CoverageService
from server.services.geospatial.runtime_registry import RuntimeRegistrySnapshot

###############################################################################
class CandidateRanker:
    def __init__(self, *, coverage_service: CoverageService) -> None:
        self.coverage_service = coverage_service

    def apply_intent_match(self, candidate: CapabilityCandidate, turn: TurnParseResult) -> float:
        score = candidate.score
        intent = turn.normalized_intent.intent_id
        if intent == "weather" and "weather" in candidate.capability_id:
            score += 0.25
        if intent == "air_quality" and "air_quality" in candidate.capability_id:
            score += 0.25
        if intent == "poi" and "poi" in candidate.capability_id:
            score += 0.25
        return score

    def apply_temporal_match(self, score: float, turn: TurnParseResult) -> float:
        if turn.temporal_signal.mode == "forecast":
            return score + 0.08
        return score

    def apply_runtime_penalties(self, candidate: CapabilityCandidate, runtime_snapshot: RuntimeRegistrySnapshot) -> float:
        profile = runtime_snapshot.profiles.get(candidate.capability_id) or {}
        if not profile.get("enabled_by_default", False):
            return -1.0
        if profile.get("credential_provider") and profile.get("credential_provider") in {"tomtom", "geoapify"}:
            # Penalize potentially unavailable credentialed capabilities unless explicitly needed.
            return -0.1
        return 0.0

    def apply_coverage_penalties(self, candidate: CapabilityCandidate, location: ResolvedLocation) -> float:
        return -0.8 if not self.coverage_service.is_location_supported(candidate.capability_id, location) else 0.0

    def rerank(
        self,
        candidates: list[CapabilityCandidate],
        turn: TurnParseResult,
        resolved_location: ResolvedLocation,
        runtime_snapshot: RuntimeRegistrySnapshot,
    ) -> list[CapabilityCandidate]:
        scored: list[tuple[float, CapabilityCandidate]] = []
        for candidate in candidates:
            score = self.apply_intent_match(candidate, turn)
            score = self.apply_temporal_match(score, turn)
            score += self.apply_runtime_penalties(candidate, runtime_snapshot)
            score += self.apply_coverage_penalties(candidate, resolved_location)
            scored.append((score, candidate.model_copy(update={"score": score})))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [item[1] for item in scored]
