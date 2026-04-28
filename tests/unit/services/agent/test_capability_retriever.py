from __future__ import annotations

from AEGIS.server.domain.extraction.models import (
    ConversationContextSnapshot,
    NormalizedIntent,
    TemporalSignal,
    TurnParseResult,
)
from AEGIS.server.services.agent.capability_retriever import CapabilityRetriever


def test_capability_retriever_returns_candidates() -> None:
    retriever = CapabilityRetriever()
    turn = TurnParseResult(
        user_text="show rain around Rome",
        conversation_context=ConversationContextSnapshot(recent_messages=[], memory_snapshot={}),
        task_class="map_search",
        location_signals=[],
        normalized_intent=NormalizedIntent(
            intent_id="weather",
            intent_label="Weather",
            task_tags=["environment"],
            intent_tags=["weather"],
            requires_location=True,
        ),
        temporal_signal=TemporalSignal(mode="forecast"),
        ambiguities=[],
        disallowed_patterns=[],
        parser_confidence=0.8,
    )
    candidates = retriever.retrieve_candidates(turn)
    assert isinstance(candidates, list)


def test_capability_retriever_uses_manifest_ranking_without_vector_bootstrap() -> None:
    retriever = CapabilityRetriever()
    turn = TurnParseResult(
        user_text="show where rain is moving around Naples right now",
        conversation_context=ConversationContextSnapshot(recent_messages=[], memory_snapshot={}),
        task_class="map_search",
        location_signals=[],
        normalized_intent=NormalizedIntent(
            intent_id="precipitation",
            intent_label="Precipitation map",
            task_tags=["rain", "storm"],
            intent_tags=["precipitation"],
            requested_visualizations=["precipitation"],
            requires_location=True,
        ),
        temporal_signal=TemporalSignal(mode="current"),
        ambiguities=[],
        disallowed_patterns=[],
        parser_confidence=0.9,
    )

    candidates = retriever.retrieve_candidates(turn)

    candidate_ids = {item.capability_id for item in candidates}
    assert "rainviewer_precipitation_radar" in candidate_ids
    assert "IMERG_Precipitation_Rate" in candidate_ids
