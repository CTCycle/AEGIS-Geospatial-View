from __future__ import annotations

import asyncio

from AEGIS.server.domain.extraction.models import (
    ConversationContextSnapshot,
    LocationSignal,
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
    task_class: str = "map_search",
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


def test_policy_engine_keeps_weather_forecast_when_radar_is_also_requested() -> None:
    engine = PolicyEngine(
        location_resolver=LocationResolver(),
        capability_retriever=CapabilityRetriever(),
    )
    turn = _turn(
        user_text="Show weather forecast and rain radar around Naples",
        intent_id="weather_forecast_rain_radar",
        task_tags=["weather", "radar"],
        intent_tags=["weather", "forecast", "rain", "radar"],
    )
    candidates = [
        CapabilityCandidate(
            capability_id="rainviewer_precipitation_radar",
            kind="overlay",
            provider="rainviewer",
            score=0.2,
        ),
        CapabilityCandidate(
            capability_id="openmeteo_weather_forecast",
            kind="overlay",
            provider="openmeteo",
            score=0.2,
        ),
        CapabilityCandidate(
            capability_id="openmeteo_air_quality_forecast",
            kind="overlay",
            provider="openmeteo",
            score=0.2,
        ),
    ]

    assert engine._select_overlays(turn, candidates) == [
        "rainviewer_precipitation_radar",
        "openmeteo_weather_forecast",
    ]


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


def test_policy_engine_renders_display_direct_query_with_overlays_as_map() -> None:
    engine = PolicyEngine(
        location_resolver=LocationResolver(),
        capability_retriever=CapabilityRetriever(),
    )
    turn = _turn(
        user_text="Show weather forecast and rain radar around Naples, Italy.",
        intent_id="weather_forecast_rain_radar",
        task_tags=["weather", "radar"],
        intent_tags=["weather", "rain", "radar"],
        task_class="direct_query",
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


def test_policy_engine_keeps_coordinate_direct_query_as_tool() -> None:
    engine = PolicyEngine(
        location_resolver=LocationResolver(),
        capability_retriever=CapabilityRetriever(),
    )
    turn = _turn(
        user_text="Convert Shibuya Crossing to coordinates only.",
        intent_id="convert_location_to_coordinates",
        task_tags=["coordinates"],
        intent_tags=["geocode"],
        task_class="direct_query",
    )
    candidates = [
        CapabilityCandidate(
            capability_id="location_to_coordinates",
            kind="tool",
            provider="nominatim",
            score=0.2,
            supports_direct_text=True,
            supports_map=False,
        ),
    ]

    mode, tool = engine._select_execution_mode(turn, candidates)

    assert mode == "direct_tool"
    assert tool is not None
    assert tool.capability_id == "location_to_coordinates"


def test_policy_engine_clarifies_deictic_reference_without_memory_before_resolving() -> None:
    engine = PolicyEngine(
        location_resolver=LocationResolver(),
        capability_retriever=CapabilityRetriever(),
    )
    turn = TurnParseResult(
        user_text="Show traffic there",
        conversation_context=ConversationContextSnapshot(recent_messages=[], memory_snapshot={}),
        task_class="map_search",
        location_signals=[
            LocationSignal(
                signal_type="deictic",
                raw_value="there",
                normalized_value="there",
                confidence=0.8,
                source="model",
            )
        ],
        normalized_intent=NormalizedIntent(
            intent_id="traffic",
            intent_label="Traffic",
            task_tags=["traffic", "map"],
            intent_tags=["traffic"],
            requires_location=True,
        ),
        temporal_signal=TemporalSignal(mode="current"),
        ambiguities=["deictic_without_memory"],
        disallowed_patterns=[],
        parser_confidence=0.65,
    )

    async def _run() -> None:
        decision = await engine.decide(
            turn=turn,
            memory_snapshot={},
            runtime_registry=RuntimeRegistry().build_snapshot(),
            capability_registry=CapabilityRegistry(),
        )
        assert decision.plan.state == "clarify"
        assert decision.clarification is not None
        assert decision.clarification.missing_fields == ["location"]

    asyncio.run(_run())


def test_policy_engine_ranks_fire_and_land_cover_over_generic_satellite_layers() -> None:
    engine = PolicyEngine(
        location_resolver=LocationResolver(),
        capability_retriever=CapabilityRetriever(),
    )
    turn = _turn(
        user_text="Show active fires and land cover around Sicily on satellite",
        intent_id="active_fires_land_cover",
        task_tags=["map", "satellite", "active_fires", "land_cover"],
        intent_tags=["active fires", "land cover", "satellite"],
    )
    candidates = [
        CapabilityCandidate(
            capability_id="VIIRS_SNPP_CorrectedReflectance_TrueColor",
            kind="overlay",
            provider="gibs",
            score=0.8,
        ),
        CapabilityCandidate(
            capability_id="VIIRS_SNPP_DayNightBand_ENCC",
            kind="overlay",
            provider="gibs",
            score=0.7,
        ),
        CapabilityCandidate(
            capability_id="MODIS_Terra_Land_Surface_Temp_Day",
            kind="overlay",
            provider="gibs",
            score=0.6,
        ),
        CapabilityCandidate(
            capability_id="MODIS_Combined_Thermal_Anomalies_Fire",
            kind="overlay",
            provider="gibs",
            score=0.2,
        ),
        CapabilityCandidate(
            capability_id="MODIS_Combined_L3_IGBP_Land_Cover_Type_Annual",
            kind="overlay",
            provider="gibs",
            score=0.2,
        ),
        CapabilityCandidate(
            capability_id="esa_worldcover",
            kind="overlay",
            provider="esa",
            score=0.1,
        ),
    ]

    selected = engine._select_overlays(turn, candidates)

    assert selected[:2] == [
        "MODIS_Combined_Thermal_Anomalies_Fire",
        "MODIS_Combined_L3_IGBP_Land_Cover_Type_Annual",
    ]
    assert "VIIRS_SNPP_CorrectedReflectance_TrueColor" not in selected
