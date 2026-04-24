from __future__ import annotations

import asyncio

from AEGIS.server.domain.extraction.models import (
    ConversationContextSnapshot,
    NormalizedIntent,
    TemporalSignal,
    TurnParseResult,
)
from AEGIS.server.domain.agent.decision import CapabilityCandidate
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


def _turn(
    *,
    user_text: str,
    intent_id: str,
    task_tags: list[str],
    intent_tags: list[str],
) -> TurnParseResult:
    return TurnParseResult(
        user_text=user_text,
        conversation_context=ConversationContextSnapshot(
            recent_messages=[],
            memory_snapshot={},
        ),
        task_class="map_search",
        location_signals=[],
        normalized_intent=NormalizedIntent(
            intent_id=intent_id,
            intent_label=intent_id.replace("_", " ").title(),
            task_tags=task_tags,
            intent_tags=intent_tags,
            requires_location=True,
        ),
        temporal_signal=TemporalSignal(mode="current"),
        ambiguities=[],
        disallowed_patterns=[],
        parser_confidence=0.8,
    )


def test_policy_engine_honors_satellite_basemap_from_intent_tags() -> None:
    engine = PolicyEngine(
        location_resolver=LocationResolver(),
        capability_retriever=CapabilityRetriever(),
    )
    turn = _turn(
        user_text="Show me Rome with air quality overlay on satellite imagery",
        intent_id="show_air_quality_overlay_rome",
        task_tags=["map", "air_quality", "satellite_imagery"],
        intent_tags=["air_quality", "overlay", "satellite"],
    )

    assert engine._select_basemap(turn, []) == "gibs_satellite"


def test_policy_engine_filters_unrelated_zero_score_overlays() -> None:
    engine = PolicyEngine(
        location_resolver=LocationResolver(),
        capability_retriever=CapabilityRetriever(),
    )
    turn = _turn(
        user_text="Show Tokyo precipitation radar on a dark map",
        intent_id="show_precipitation_radar",
        task_tags=["weather", "radar", "map", "precipitation"],
        intent_tags=["precipitation", "radar", "dark_map"],
    )
    candidates = [
        CapabilityCandidate(
            capability_id="rainviewer_precipitation_radar",
            kind="overlay",
            provider="rainviewer",
            score=0.17,
        ),
        CapabilityCandidate(
            capability_id="IMERG_Precipitation_Rate",
            kind="overlay",
            provider="gibs",
            score=0.0,
        ),
        CapabilityCandidate(
            capability_id="openmeteo_air_quality_forecast",
            kind="overlay",
            provider="openmeteo",
            score=0.0,
        ),
    ]

    assert engine._select_overlays(turn, candidates) == ["rainviewer_precipitation_radar"]


def test_policy_engine_selects_traffic_overlay_for_traffic_intent() -> None:
    engine = PolicyEngine(
        location_resolver=LocationResolver(),
        capability_retriever=CapabilityRetriever(),
    )
    turn = _turn(
        user_text="Show current traffic flow around Times Square",
        intent_id="show_current_traffic_flow",
        task_tags=["traffic", "map"],
        intent_tags=["traffic", "flow"],
    )
    candidates = [
        CapabilityCandidate(
            capability_id="tomtom_traffic_flow",
            kind="overlay",
            provider="tomtom",
            score=0.0,
        ),
        CapabilityCandidate(
            capability_id="openmeteo_air_quality_forecast",
            kind="overlay",
            provider="openmeteo",
            score=0.2,
        ),
    ]

    assert engine._select_overlays(turn, candidates) == ["tomtom_traffic_flow"]


def test_policy_engine_does_not_treat_satellite_basemap_as_overlay_topic() -> None:
    engine = PolicyEngine(
        location_resolver=LocationResolver(),
        capability_retriever=CapabilityRetriever(),
    )
    turn = _turn(
        user_text="Show Rome with air quality overlay on satellite imagery",
        intent_id="show_air_quality_rome_satellite",
        task_tags=["map", "air_quality", "satellite_imagery"],
        intent_tags=["air_quality", "overlay", "satellite"],
    )
    candidates = [
        CapabilityCandidate(
            capability_id="openaq_air_quality",
            kind="overlay",
            provider="openaq",
            score=0.2,
        ),
        CapabilityCandidate(
            capability_id="VIIRS_SNPP_CorrectedReflectance_TrueColor",
            kind="overlay",
            provider="gibs",
            score=0.1,
        ),
    ]

    assert engine._select_overlays(turn, candidates) == ["openaq_air_quality"]
