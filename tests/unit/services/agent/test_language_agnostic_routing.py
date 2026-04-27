from __future__ import annotations

from AEGIS.server.domain.agent.decision import CapabilityCandidate
from AEGIS.server.domain.extraction.models import (
    ConversationContextSnapshot,
    DisallowedPattern,
    NormalizedIntent,
    TemporalSignal,
    TurnParseResult,
)
from AEGIS.server.services.agent.capability_retriever import CapabilityRetriever
from AEGIS.server.services.agent.location_resolver import LocationResolver
from AEGIS.server.services.agent.manifest_intent_resolver import ManifestIntentResolver
from AEGIS.server.services.agent.policy_engine import PolicyEngine
from AEGIS.server.services.geospatial.capability_registry import CapabilityRegistry
from AEGIS.server.services.geospatial.runtime_registry import RuntimeRegistry


def _turn(
    *,
    user_text: str,
    task_class: str,
    intent_id: str,
    intent_label: str,
    task_tags: list[str],
    intent_tags: list[str],
    requested_visualizations: list[str],
) -> TurnParseResult:
    return TurnParseResult(
        user_text=user_text,
        conversation_context=ConversationContextSnapshot(
            recent_messages=[],
            memory_snapshot={},
        ),
        task_class=task_class,
        location_signals=[],
        normalized_intent=NormalizedIntent(
            intent_id=intent_id,
            intent_label=intent_label,
            task_tags=task_tags,
            intent_tags=intent_tags,
            requested_visualizations=requested_visualizations,
            requires_location=True,
        ),
        temporal_signal=TemporalSignal(mode="current"),
        ambiguities=[],
        disallowed_patterns=[],
        parser_confidence=0.9,
    )


def test_manifest_resolver_routes_non_english_query_from_structured_signals() -> None:
    turn = _turn(
        user_text="Affiche les précipitations et la météo autour de Naples.",
        task_class="map_search",
        intent_id="meteo_precipitations_naples",
        intent_label="Météo et précipitations",
        task_tags=["map", "weather"],
        intent_tags=["weather", "precipitation", "radar"],
        requested_visualizations=["weather", "precipitation"],
    )
    runtime_snapshot = RuntimeRegistry().build_snapshot()
    available_ids = {
        capability_id
        for capability_id, profile in runtime_snapshot.profiles.items()
        if isinstance(profile, dict) and bool(profile.get("enabled_by_default", False))
    }

    resolution = ManifestIntentResolver().resolve(
        turn=turn,
        capability_registry=CapabilityRegistry(),
        available_ids=available_ids,
    )

    assert "rainviewer_precipitation_radar" in resolution.overlay_ids
    assert resolution.tool_id == "get_weather_forecast"


def test_direct_query_map_routing_does_not_depend_on_english_display_markers() -> None:
    engine = PolicyEngine(
        location_resolver=LocationResolver(),
        capability_retriever=CapabilityRetriever(),
    )
    turn = _turn(
        user_text="Mostra radar pioggia e previsione meteo per Napoli",
        task_class="direct_query",
        intent_id="previsione_meteo_radar",
        intent_label="Previsione meteo con radar",
        task_tags=["weather", "radar"],
        intent_tags=["weather", "forecast", "precipitation"],
        requested_visualizations=["weather", "precipitation"],
    )
    candidates = [
        CapabilityCandidate(
            capability_id="rainviewer_precipitation_radar",
            kind="overlay",
            provider="rainviewer",
            score=0.1,
        ),
        CapabilityCandidate(
            capability_id="get_weather_forecast",
            kind="tool",
            provider="openmeteo",
            score=0.2,
            supports_direct_text=True,
            supports_map=True,
        ),
    ]

    mode, tool = engine._select_execution_mode(turn, candidates)

    assert mode == "map_search"
    assert tool is None


def test_overlay_suppression_uses_structured_policy_signals() -> None:
    engine = PolicyEngine(
        location_resolver=LocationResolver(),
        capability_retriever=CapabilityRetriever(),
    )
    turn = _turn(
        user_text="Usa solo lo stile mappa base",
        task_class="map_search",
        intent_id="stile_mappa_base",
        intent_label="Solo basemap",
        task_tags=["map"],
        intent_tags=["basemap_only"],
        requested_visualizations=[],
    )
    turn = turn.model_copy(
        update={
            "disallowed_patterns": [
                DisallowedPattern(
                    pattern_id="overlay_restriction",
                    reason="Overlay explicitly disallowed by user intent.",
                    matched_text="solo mappa base",
                )
            ]
        }
    )

    assert engine._explicitly_suppresses_overlays(turn) is True
