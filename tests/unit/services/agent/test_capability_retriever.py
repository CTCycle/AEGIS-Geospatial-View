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
