"""Tests for the agent pipeline map_session population chain."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from server.domain.agent.decision import (
    PolicyDecision,
    ResolvedLocation,
)
from server.domain.chat import ChatTurnResponse
from server.domain.extraction.models import NormalizedAction, TurnParseResult
from server.domain.geographics import MapSession, ViewportPolicy
from server.services.agent.native_tool_loop import (
    AgentToolLoopResult,
    LLMToolResult,
    NativeToolLoop,
)
from server.services.agent.orchestrator import AgentOrchestrator

###############################################################################
# Helpers
###############################################################################

def make_map_session(
    *,
    session_id: str = "map-123",
    basemap_id: str = "osm_default",
    overlay_ids: list[str] | None = None,
    latitude: float = 48.8566,
    longitude: float = 2.3522,
) -> MapSession:
    return MapSession(
        session_id=session_id,
        resolved_location=ResolvedLocation(
            label="Paris",
            latitude=latitude,
            longitude=longitude,
            country="France",
            city="Paris",
            source="nominatim",
            confidence=0.95,
        ),
        basemap_id=basemap_id,
        overlay_ids=overlay_ids or [],
        viewport=ViewportPolicy(
            center_latitude=latitude,
            center_longitude=longitude,
            radius_m=2500,
        ),
        generated_at=datetime.now(UTC),
        payload={"action_id": "map_search"},
        center={"latitude": latitude, "longitude": longitude},
        bounds=[2.0, 48.5, 2.5, 49.0],
        basemap={"id": basemap_id, "provider": "osm"},
        overlays=[],
        compliance_warnings=[],
    )


def make_tool_result(
    *,
    operation: str,
    map_session: dict | None = None,
    capability_selection: dict | None = None,
    capability_id: str = "test_capability",
    is_error: bool = False,
) -> LLMToolResult:
    data: dict[str, Any] = {
        "ok": not is_error,
        "operation": operation,
        "capability_id": capability_id,
    }
    if map_session is not None:
        data["map_session"] = map_session
    if capability_selection is not None:
        data["capability_selection"] = capability_selection
    content = {
        "ok": not is_error,
        "data": data,
        "error": None,
        "metadata": {},
    }
    return LLMToolResult(
        tool_call_id="call_1",
        name="execute_geospatial_capability",
        content=content,
        is_error=is_error,
        error=None,
    )


###############################################################################
# Tests: NativeToolLoop._extract_map_session
###############################################################################

class TestExtractMapSession:
    def test_empty_results_returns_none(self):
        result = NativeToolLoop._extract_map_session([])
        assert result is None

    def test_no_map_session_in_results_returns_none(self):
        results = [
            make_tool_result(operation="capability_selection_created"),
            make_tool_result(operation="validated_only"),
        ]
        result = NativeToolLoop._extract_map_session(results)
        assert result is None

    def test_map_session_created_returns_validated_session(self):
        ms = make_map_session()
        ms_raw = ms.model_dump(mode="json")
        results = [
            make_tool_result(operation="map_session_created", map_session=ms_raw),
        ]
        result = NativeToolLoop._extract_map_session(results)
        assert result is not None
        assert result.session_id == ms.session_id
        assert result.basemap_id == ms.basemap_id

    def test_multiple_results_picks_first_map_session(self):
        ms1 = make_map_session(session_id="map-1", basemap_id="gibs_satellite")
        ms2 = make_map_session(session_id="map-2", basemap_id="osm_default")
        results = [
            make_tool_result(operation="capability_selection_created", capability_id="basemap_a"),
            make_tool_result(operation="map_session_created", map_session=ms1.model_dump(mode="json")),
            make_tool_result(operation="map_session_created", map_session=ms2.model_dump(mode="json")),
        ]
        result = NativeToolLoop._extract_map_session(results)
        assert result is not None
        assert result.session_id == "map-1"

    def test_malformed_map_session_dict_returns_none(self):
        results = [
            make_tool_result(
                operation="map_session_created",
                map_session={"session_id": "incomplete"},
            ),
        ]
        result = NativeToolLoop._extract_map_session(results)
        assert result is None

    def test_error_results_are_skipped(self):
        ms = make_map_session()
        results = [
            make_tool_result(operation="map_session_created", map_session=ms.model_dump(mode="json"), is_error=False),
            make_tool_result(operation="map_session_created", map_session={}, is_error=True),
        ]
        result = NativeToolLoop._extract_map_session(results)
        assert result is not None
        assert result.session_id == ms.session_id


###############################################################################
# Tests: AgentOrchestrator._build_combined_map_session_from_tool_results
###############################################################################

def make_tool_payload(
    tool_results_data: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build a tool_payload dict from raw tool result data dicts."""
    return {
        "tool_calls": [],
        "tool_results": [
            {
                "tool_call_id": "call_1",
                "name": "execute_geospatial_capability",
                "content": data,
                "is_error": not data.get("ok", True),
                "error": None,
            }
            for data in tool_results_data
        ],
        "iterations": 1,
        "stopped_reason": "final",
    }


def _make_turn_contract(action_id: str = "map_search") -> MagicMock:
    tc = MagicMock(spec=TurnParseResult)
    tc.location_signals = []
    tc.task_class = "map_search"
    tc.user_text = "show satellite imagery of Paris"
    tc.normalized_action = NormalizedAction(
        action_id=action_id,
        action_label=action_id,
        task_tags=[],
        action_tags=[],
        requires_location=True,
    )
    tc.ambiguities = []
    tc.disallowed_patterns = []
    tc.parser_confidence = 0.95
    tc.conversation_context = MagicMock()
    return tc


@pytest.fixture
def orchestrator():
    """Create an AgentOrchestrator with all dependencies mocked."""
    search_orch = AsyncMock()
    search_orch.execute.return_value = make_map_session()
    search_orch.capability_registry = MagicMock()

    policy_engine = MagicMock()
    policy_engine.location_resolver = AsyncMock()
    policy_engine.location_resolver.resolve_location_signals.return_value = ResolvedLocation(
        label="Paris",
        latitude=48.8566,
        longitude=2.3522,
        country="France",
        city="Paris",
        source="nominatim",
        confidence=0.95,
    )

    orchestrator = AgentOrchestrator(
        search_orchestrator=search_orch,
        parser_service=MagicMock(),
        location_memory_service=MagicMock(),
        policy_engine=policy_engine,
        tool_registry=MagicMock(),
        request_builder=MagicMock(),
    )
    orchestrator.request_builder.build_location_search_request.return_value = MagicMock()
    return orchestrator


class TestCombinedBuilder:
    async def test_none_tool_payload_returns_none(self, orchestrator):
        result = await orchestrator._build_combined_map_session_from_tool_results(
            tool_payload=None,
            turn_contract=_make_turn_contract(),
            latest_memory=None,
        )
        assert result is None

    async def test_empty_tool_results_returns_none(self, orchestrator):
        result = await orchestrator._build_combined_map_session_from_tool_results(
            tool_payload={"tool_results": []},
            turn_contract=_make_turn_contract(),
            latest_memory=None,
        )
        assert result is None

    async def test_single_basemap_selection_creates_session(self, orchestrator):
        payload = make_tool_payload([
            {
                "ok": True,
                "data": {
                    "ok": True,
                    "operation": "capability_selection_created",
                    "capability_id": "gibs_satellite",
                    "capability_selection": {
                        "basemap_id": "gibs_satellite",
                        "overlay_ids": [],
                    },
                },
            },
        ])
        result = await orchestrator._build_combined_map_session_from_tool_results(
            tool_payload=payload,
            turn_contract=_make_turn_contract(),
            latest_memory=None,
        )
        assert result is not None
        orchestrator.search_orchestrator.execute.assert_awaited_once()

    async def test_single_overlay_map_session_creates_session(self, orchestrator):
        ms = make_map_session(basemap_id="osm_default", overlay_ids=["rainviewer_radar"])
        payload = make_tool_payload([
            {
                "ok": True,
                "data": {
                    "ok": True,
                    "operation": "map_session_created",
                    "capability_id": "rainviewer_radar",
                    "map_session": ms.model_dump(mode="json"),
                },
            },
        ])
        result = await orchestrator._build_combined_map_session_from_tool_results(
            tool_payload=payload,
            turn_contract=_make_turn_contract(),
            latest_memory=None,
        )
        assert result is not None
        orchestrator.search_orchestrator.execute.assert_awaited_once()

    async def test_basemap_plus_overlay_combined_session(self, orchestrator):
        payload = make_tool_payload([
            {
                "ok": True,
                "data": {
                    "ok": True,
                    "operation": "capability_selection_created",
                    "capability_id": "gibs_satellite",
                    "capability_selection": {
                        "basemap_id": "gibs_satellite",
                        "overlay_ids": [],
                    },
                },
            },
            {
                "ok": True,
                "data": {
                    "ok": True,
                    "operation": "map_session_created",
                    "capability_id": "rainviewer_radar",
                    "map_session": make_map_session(
                        basemap_id="osm_default",
                        overlay_ids=["rainviewer_radar"],
                    ).model_dump(mode="json"),
                },
            },
        ])
        result = await orchestrator._build_combined_map_session_from_tool_results(
            tool_payload=payload,
            turn_contract=_make_turn_contract(),
            latest_memory=None,
        )
        assert result is not None
        orchestrator.search_orchestrator.execute.assert_awaited_once()

    async def test_multiple_overlays_merged_into_one_session(self, orchestrator):
        """Multiple tool results (basemap + 2 overlays) are merged into one combined MapSession."""
        payload = make_tool_payload([
            {
                "ok": True,
                "data": {
                    "ok": True,
                    "operation": "map_session_created",
                    "capability_id": "gibs_satellite",
                    "map_session": make_map_session(
                        basemap_id="gibs_satellite",
                        overlay_ids=[],
                    ).model_dump(mode="json"),
                },
            },
            {
                "ok": True,
                "data": {
                    "ok": True,
                    "operation": "map_session_created",
                    "capability_id": "rainviewer_radar",
                    "map_session": make_map_session(
                        basemap_id="osm_default",
                        overlay_ids=["rainviewer_radar"],
                    ).model_dump(mode="json"),
                },
            },
            {
                "ok": True,
                "data": {
                    "ok": True,
                    "operation": "map_session_created",
                    "capability_id": "tomtom_traffic_flow",
                    "map_session": make_map_session(
                        basemap_id="osm_default",
                        overlay_ids=["tomtom_traffic_flow"],
                    ).model_dump(mode="json"),
                },
            },
        ])
        result = await orchestrator._build_combined_map_session_from_tool_results(
            tool_payload=payload,
            turn_contract=_make_turn_contract(),
            latest_memory=None,
        )
        assert result is not None
        orchestrator.search_orchestrator.execute.assert_awaited_once()

    async def test_validated_only_results_returns_none(self, orchestrator):
        payload = make_tool_payload([
            {
                "ok": True,
                "data": {
                    "ok": True,
                    "operation": "validated_only",
                    "capability_id": "test_capability",
                    "map_session": None,
                    "capability_selection": None,
                },
            },
        ])
        result = await orchestrator._build_combined_map_session_from_tool_results(
            tool_payload=payload,
            turn_contract=_make_turn_contract(),
            latest_memory=None,
        )
        assert result is None

    async def test_all_error_results_returns_none(self, orchestrator):
        payload = make_tool_payload([
            {
                "ok": False,
                "data": None,
                "error": {"code": "tool_error", "message": "Failed"},
            },
        ])
        result = await orchestrator._build_combined_map_session_from_tool_results(
            tool_payload=payload,
            turn_contract=_make_turn_contract(),
            latest_memory=None,
        )
        assert result is None


###############################################################################
# Tests: Post-processing priority chain
###############################################################################

def test_agent_tool_loop_result_map_session_field():
    """AgentToolLoopResult accepts the new map_session field."""
    ms = make_map_session()
    result = AgentToolLoopResult(
        final_text="Map ready for Paris.",
        tool_calls=[],
        tool_results=[],
        iterations=1,
        stopped_reason="final",
        map_session=ms,
    )
    assert result.map_session is ms


def test_agent_tool_loop_result_map_session_defaults_none():
    """map_session defaults to None for backward compatibility."""
    result = AgentToolLoopResult(
        final_text="Done.",
        tool_calls=[],
        tool_results=[],
        iterations=1,
        stopped_reason="final",
    )
    assert result.map_session is None


def test_agent_tool_loop_result_map_session_in_turn_response():
    """Verify map_session flows through ChatTurnResponse model."""
    ms = make_map_session()
    response = ChatTurnResponse(
        request_id="test-1",
        session_id=42,
        assistant_message="Map ready.",
        turn_contract=MagicMock(spec=TurnParseResult),
        decision=MagicMock(spec=PolicyDecision),
        map_session=ms,
        memory_snapshot={},
    )
    assert response.map_session is ms
    assert response.map_session.session_id == "map-123"
