from __future__ import annotations

import asyncio

from AEGIS.server.domain.extraction.models import (
    ConversationContextSnapshot,
    NormalizedIntent,
    TemporalSignal,
    TurnParseResult,
)
from AEGIS.server.services.agent.capability_retriever import CapabilityRetriever
from AEGIS.server.services.agent.location_resolver import LocationResolver
from AEGIS.server.services.agent.policy_engine import PolicyEngine
from AEGIS.server.services.geospatial.capability_registry import CapabilityRegistry
from AEGIS.server.services.geospatial.runtime_registry import RuntimeRegistry


def test_policy_engine_clarifies_when_location_missing() -> None:
    engine = PolicyEngine(
        location_resolver=LocationResolver(),
        capability_retriever=CapabilityRetriever(),
    )
    turn = TurnParseResult(
        user_text="show air quality",
        conversation_context=ConversationContextSnapshot(recent_messages=[], memory_snapshot={}),
        task_class="map_search",
        location_signals=[],
        normalized_intent=NormalizedIntent(
            intent_id="air_quality",
            intent_label="Air quality",
            task_tags=["environment"],
            intent_tags=["air quality"],
            requires_location=True,
        ),
        temporal_signal=TemporalSignal(mode="current"),
        ambiguities=[],
        disallowed_patterns=[],
        parser_confidence=0.8,
    )

    async def _run() -> None:
        decision = await engine.decide(
            turn=turn,
            memory_snapshot={},
            runtime_registry=RuntimeRegistry().build_snapshot(),
            capability_registry=CapabilityRegistry(),
        )
        assert decision.plan.state == "clarify"

    asyncio.run(_run())
