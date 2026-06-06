from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from server.domain.agent.decision import (
    ClarificationRequest,
    DecisionTrace,
    ExecutionPlan,
    PolicyDecision,
    ResolvedLocation,
)
from server.domain.chat import ChatTurnRequest
from server.domain.extraction.models import (
    ConversationContextSnapshot,
    LocationSignal,
    NormalizedAction,
    TurnParseResult,
)
from server.domain.geographics import MapSession
from server.services.agent.location_memory import LocationMemoryService
from server.services.agent.native_tool_loop import AgentToolLoopResult
from server.services.agent.orchestrator import AgentOrchestrator
from server.services.agent.policy_engine import AgentPolicyConstraints
from server.services.agent.tool_registry import ToolRegistry
from server.services.llm.types import LLMToolCall, LLMToolDefinition, LLMToolResult


@dataclass
class _Session:
    id: int = 7


@dataclass
class _Settings:
    agent_model_provider: str = "openai"
    agent_model_name: str = "gpt-4.1"


class _HistoryRepo:
    def __init__(self, latest_memory: dict[str, Any] | None = None) -> None:
        self.messages: list[dict[str, Any]] = []
        self.latest_memory = latest_memory or {}

    def upsert_session(self, session_id, title=None):  # noqa: ANN001
        return _Session(id=session_id or 7)

    def append_message(self, **kwargs: Any) -> None:
        self.messages.append(kwargs)

    def list_recent_messages(self, session_id: int, limit: int) -> list[dict[str, Any]]:
        return []

    def get_latest_turn_contract(self, session_id: int):
        return None

    def get_latest_memory_snapshot(self, session_id: int) -> dict[str, Any]:
        return self.latest_memory


class _Parser:
    last_context_usage = None

    def parse_turn(
        self,
        user_message: str,
        memory_snapshot: dict,
        conversation_messages: list[dict],
    ) -> TurnParseResult:
        return TurnParseResult(
            user_text=user_message,
            conversation_context=ConversationContextSnapshot(
                recent_messages=[],
                memory_snapshot=memory_snapshot,
            ),
            task_class="map_search",
            location_signals=[
                LocationSignal(
                    signal_type="city",
                    raw_value="Rome",
                    normalized_value="Rome",
                    latitude=41.9028,
                    longitude=12.4964,
                    confidence=0.9,
                )
            ],
            normalized_action=NormalizedAction(
                action_id="map_search",
                action_label="Map Search",
                task_tags=["map"],
                action_tags=["catalog"],
                requires_location=True,
            ),
            parser_confidence=0.9,
        )


class _DeicticParser(_Parser):
    def parse_turn(
        self,
        user_message: str,
        memory_snapshot: dict,
        conversation_messages: list[dict],
    ) -> TurnParseResult:
        return TurnParseResult(
            user_text=user_message,
            conversation_context=ConversationContextSnapshot(
                recent_messages=[],
                memory_snapshot=memory_snapshot,
            ),
            task_class="direct_query",
            location_signals=[],
            normalized_action=NormalizedAction(
                action_id="get_weather_forecast",
                action_label="Weather Forecast",
                task_tags=["weather"],
                action_tags=["direct"],
                requires_location=True,
            ),
            ambiguities=["missing_location", "deictic_without_memory"],
            parser_confidence=0.9,
        )


class _ParisParser(_Parser):
    def parse_turn(
        self,
        user_message: str,
        memory_snapshot: dict,
        conversation_messages: list[dict],
    ) -> TurnParseResult:
        return TurnParseResult(
            user_text=user_message,
            conversation_context=ConversationContextSnapshot(
                recent_messages=[],
                memory_snapshot=memory_snapshot,
            ),
            task_class="map_search",
            location_signals=[
                LocationSignal(
                    signal_type="city",
                    raw_value="Paris",
                    normalized_value="Paris",
                    latitude=48.8566,
                    longitude=2.3522,
                    confidence=0.9,
                )
            ],
            normalized_action=NormalizedAction(
                action_id="map_search",
                action_label="Map Search",
                task_tags=["map"],
                action_tags=["catalog"],
                requires_location=True,
            ),
            parser_confidence=0.9,
        )


class _DirectToolParser(_Parser):
    def parse_turn(
        self,
        user_message: str,
        memory_snapshot: dict,
        conversation_messages: list[dict],
    ) -> TurnParseResult:
        return TurnParseResult(
            user_text=user_message,
            conversation_context=ConversationContextSnapshot(
                recent_messages=[],
                memory_snapshot=memory_snapshot,
            ),
            task_class="direct_query",
            location_signals=[
                LocationSignal(
                    signal_type="city",
                    raw_value="Rome",
                    normalized_value="Rome",
                    latitude=41.9028,
                    longitude=12.4964,
                    confidence=0.9,
                )
            ],
            normalized_action=NormalizedAction(
                action_id="location_to_coordinates",
                action_label="Location To Coordinates",
                task_tags=["coordinates"],
                action_tags=["direct"],
                requires_location=True,
            ),
            parser_confidence=0.9,
        )


class _LocationResolver:
    async def resolve_location_signals(self, location_signals, memory_snapshot):  # noqa: ANN001
        signal = location_signals[0]
        return ResolvedLocation(
            label=signal.normalized_value or signal.raw_value,
            latitude=float(signal.latitude or 41.9028),
            longitude=float(signal.longitude or 12.4964),
            source=signal.source,
            confidence=signal.confidence,
        )


class _Policy:
    def __init__(self) -> None:
        self.preflight_calls = 0
        self.location_resolver = _LocationResolver()

    def build_agent_constraints(self, parsed_request, map_state):
        return AgentPolicyConstraints(
            requires_location=True,
            allowed_tool_names=["execute_geospatial_capability", "list_geospatial_capabilities"],
        )

    def evaluate_preflight(self, turn):
        self.preflight_calls += 1
        return None


class _ClarifyingPolicy(_Policy):
    def evaluate_preflight(self, turn):
        self.preflight_calls += 1
        return PolicyDecision(
            plan=ExecutionPlan(
                state="clarify",
                mode="direct_text",
                action_id=turn.normalized_action.action_id,
            ),
            clarification=ClarificationRequest(
                question="Which location should I use?",
                reason="Location is required for this action.",
                missing_fields=["location"],
            ),
            trace=DecisionTrace(steps=["clarify"]),
        )


class _RejectingPolicy(_Policy):
    def evaluate_preflight(self, turn):
        self.preflight_calls += 1
        return PolicyDecision(
            plan=ExecutionPlan(
                state="reject",
                mode="direct_text",
                action_id=turn.normalized_action.action_id,
            ),
            clarification=ClarificationRequest(
                question="I cannot execute this request with the current policy constraints.",
                reason="Policy blocked the request.",
                missing_fields=[],
            ),
            trace=DecisionTrace(steps=["reject"]),
        )


class _Catalog:
    def register_with(self, registry: ToolRegistry) -> None:
        registry.register_native_tool(
            LLMToolDefinition(
                name="execute_geospatial_capability",
                description="Execute",
                parameters_json_schema={
                    "type": "object",
                    "properties": {
                        "capability_id": {"type": "string"},
                        "arguments": {"type": "object"},
                    },
                    "required": ["capability_id", "arguments"],
                },
            ),
            self._handler,
        )

    async def _handler(self, arguments: dict[str, Any], context: Any) -> dict[str, Any]:
        _ = arguments, context
        return {
            "ok": True,
            "operation": "map_session_created",
            "capability_id": "weather_overlay",
            "arguments": {},
            "map_session": MapSession(
                session_id="map-1",
                resolved_location=ResolvedLocation(
                    label="Rome",
                    latitude=41.9028,
                    longitude=12.4964,
                    source="resolver",
                    confidence=0.9,
                ),
                basemap_id="osm_default",
                overlay_ids=["weather_overlay"],
                viewport={
                    "center_latitude": 41.9028,
                    "center_longitude": 12.4964,
                    "radius_m": 2500.0,
                },
                basemap={"id": "osm_default", "label": "OpenStreetMap"},
                overlays=[{"id": "weather_overlay", "label": "Weather Overlay"}],
                center={"latitude": 41.9028, "longitude": 12.4964},
                bounds=[12.0, 41.0, 13.0, 42.0],
            ).model_dump(mode="json"),
            "direct_result": None,
            "capability_selection": None,
            "observations": [],
            "warnings": [],
            "error": None,
            "metadata": {},
        }


class _FallbackCatalog:
    def register_with(self, registry: ToolRegistry) -> None:
        registry.register_native_tool(
            LLMToolDefinition(
                name="list_geospatial_capabilities",
                description="List",
                parameters_json_schema={"type": "object", "properties": {}},
            ),
            self._handler,
        )

    async def _handler(self, arguments: dict[str, Any], context: Any) -> dict[str, Any]:
        _ = arguments, context
        return {"items": []}


class _NativeLoop:
    def __init__(self, result: AgentToolLoopResult) -> None:
        self.result = result
        self.requests: list[Any] = []

    async def run(self, request):
        self.requests.append(request)
        return self.result


class _SettingsRepo:
    def get_or_create(self) -> _Settings:
        return _Settings()


class _SearchOrchestrator:
    def __init__(self) -> None:
        self.requests: list[Any] = []

    async def execute(self, payload):  # noqa: ANN001
        self.requests.append(payload)
        return MapSession(
            session_id="fallback-map",
            resolved_location=payload.resolved_location,
            basemap_id=payload.basemap_id,
            overlay_ids=payload.overlay_ids,
            viewport=payload.viewport,
            basemap={"id": payload.basemap_id, "label": payload.basemap_id},
            overlays=[{"id": overlay_id, "label": overlay_id} for overlay_id in payload.overlay_ids],
            payload={"action_id": payload.action_id},
            center={
                "latitude": payload.viewport.center_latitude,
                "longitude": payload.viewport.center_longitude,
            },
            bounds=[12.0, 41.0, 13.0, 42.0],
        )


class _FailingCatalog:
    def register_with(self, registry: ToolRegistry) -> None:
        registry.register_native_tool(
            LLMToolDefinition(
                name="execute_geospatial_capability",
                description="Execute",
                parameters_json_schema={
                    "type": "object",
                    "properties": {
                        "capability_id": {"type": "string"},
                        "arguments": {"type": "object"},
                    },
                    "required": ["capability_id", "arguments"],
                },
            ),
            self._handler,
        )

    async def _handler(self, arguments: dict[str, Any], context: Any) -> dict[str, Any]:
        _ = arguments, context
        return {
            "ok": False,
            "operation": "provider_error",
            "capability_id": "weather_overlay",
            "arguments": {},
            "map_session": None,
            "direct_result": None,
            "capability_selection": None,
            "observations": [],
            "warnings": [],
            "error": {"code": "provider_error", "message": "Upstream provider failed."},
            "metadata": {},
        }


class _DirectResultCatalog:
    def register_with(self, registry: ToolRegistry) -> None:
        registry.register_native_tool(
            LLMToolDefinition(
                name="execute_geospatial_capability",
                description="Execute",
                parameters_json_schema={
                    "type": "object",
                    "properties": {
                        "capability_id": {"type": "string"},
                        "arguments": {"type": "object"},
                    },
                    "required": ["capability_id", "arguments"],
                },
            ),
            self._handler,
        )

    async def _handler(self, arguments: dict[str, Any], context: Any) -> dict[str, Any]:
        _ = arguments, context
        return {
            "ok": True,
            "operation": "direct_result_created",
            "capability_id": "coordinates_tool",
            "arguments": {"location": "Rome"},
            "map_session": None,
            "direct_result": {
                "tool_id": "location_to_coordinates",
                "location": "Rome",
                "coordinates": {"latitude": 41.9028, "longitude": 12.4964},
                "result": {"coordinates": {"latitude": 41.9028, "longitude": 12.4964}},
            },
            "capability_selection": None,
            "observations": [],
            "warnings": [],
            "error": None,
            "metadata": {},
        }


def test_orchestrator_uses_verified_tool_map_session() -> None:
    async def _run() -> None:
        policy = _Policy()
        history = _HistoryRepo()
        native_loop = _NativeLoop(
            AgentToolLoopResult(
                final_text="Catalog checked.",
                tool_calls=[
                    LLMToolCall(
                        id="1",
                        name="execute_geospatial_capability",
                        arguments={"capability_id": "weather_overlay", "arguments": {}},
                    )
                ],
                tool_results=[
                    LLMToolResult(
                        tool_call_id="1",
                        name="execute_geospatial_capability",
                        content={
                            "ok": True,
                            "data": await _Catalog()._handler({}, None),
                            "error": None,
                            "metadata": {},
                        },
                    )
                ],
                iterations=1,
                stopped_reason="final",
            )
        )
        orchestrator = AgentOrchestrator(
            search_orchestrator=_SearchOrchestrator(),  # type: ignore[arg-type]
            parser_service=_Parser(),  # type: ignore[arg-type]
            location_memory_service=LocationMemoryService(),
            policy_engine=policy,  # type: ignore[arg-type]
            tool_registry=ToolRegistry(),
            request_builder=__import__(
                "server.services.search.request_builder",
                fromlist=["RequestBuilder"],
            ).RequestBuilder(),
            native_tool_loop=native_loop,  # type: ignore[arg-type]
            agent_tool_catalog_service=_Catalog(),  # type: ignore[arg-type]
            settings_repo=_SettingsRepo(),  # type: ignore[arg-type]
            history_repo=history,  # type: ignore[arg-type]
        )

        response = await orchestrator.run_turn(ChatTurnRequest(message="show Rome"))

        assert response.map_session is not None
        assert response.operation is not None
        assert response.operation.kind == "map_session"
        assert response.operation.status == "success"
        assert response.decision.plan.state == "map_search"
        assert response.decision.plan.mode == "map"
        assert response.map_session.resolved_location.label == "Rome"
        assert response.assistant_message.startswith("Map ready for Rome")
        assert response.tool_payload is not None
        assert response.tool_payload["tool_calls"][0]["name"] == "execute_geospatial_capability"
        assert policy.preflight_calls == 1

    asyncio.run(_run())


def test_orchestrator_builds_fallback_map_when_tool_loop_only_chats() -> None:
    async def _run() -> None:
        policy = _Policy()
        history = _HistoryRepo()
        search_orchestrator = _SearchOrchestrator()
        native_loop = _NativeLoop(
            AgentToolLoopResult(
                final_text="I found Rome.",
                tool_calls=[
                    LLMToolCall(
                        id="1",
                        name="list_geospatial_capabilities",
                        arguments={},
                    )
                ],
                tool_results=[
                    LLMToolResult(
                        tool_call_id="1",
                        name="list_geospatial_capabilities",
                        content={"ok": True, "data": {"items": []}, "error": None, "metadata": {}},
                    )
                ],
                iterations=1,
                stopped_reason="final",
            )
        )
        orchestrator = AgentOrchestrator(
            search_orchestrator=search_orchestrator,  # type: ignore[arg-type]
            parser_service=_Parser(),  # type: ignore[arg-type]
            location_memory_service=LocationMemoryService(),
            policy_engine=policy,  # type: ignore[arg-type]
            tool_registry=ToolRegistry(),
            request_builder=__import__(
                "server.services.search.request_builder",
                fromlist=["RequestBuilder"],
            ).RequestBuilder(),
            native_tool_loop=native_loop,  # type: ignore[arg-type]
            agent_tool_catalog_service=_FallbackCatalog(),  # type: ignore[arg-type]
            settings_repo=_SettingsRepo(),  # type: ignore[arg-type]
            history_repo=history,  # type: ignore[arg-type]
        )

        response = await orchestrator.run_turn(ChatTurnRequest(message="show Rome"))

        assert response.map_session is not None
        assert response.operation is not None
        assert response.operation.kind == "map_session"
        assert response.decision.plan.state == "map_search"
        assert response.decision.plan.mode == "map"
        assert response.map_session.resolved_location.label == "Rome"
        assert search_orchestrator.requests
        assert response.assistant_message.startswith("Map ready for Rome")

    asyncio.run(_run())


def test_orchestrator_fallback_map_infers_requested_overlay_from_user_text() -> None:
    async def _run() -> None:
        policy = _Policy()
        history = _HistoryRepo()
        search_orchestrator = _SearchOrchestrator()
        native_loop = _NativeLoop(
            AgentToolLoopResult(
                final_text="I found Rome.",
                tool_calls=[
                    LLMToolCall(
                        id="1",
                        name="list_geospatial_capabilities",
                        arguments={},
                    )
                ],
                tool_results=[
                    LLMToolResult(
                        tool_call_id="1",
                        name="list_geospatial_capabilities",
                        content={"ok": True, "data": {"items": []}, "error": None, "metadata": {}},
                    )
                ],
                iterations=1,
                stopped_reason="final",
            )
        )
        orchestrator = AgentOrchestrator(
            search_orchestrator=search_orchestrator,  # type: ignore[arg-type]
            parser_service=_Parser(),  # type: ignore[arg-type]
            location_memory_service=LocationMemoryService(),
            policy_engine=policy,  # type: ignore[arg-type]
            tool_registry=ToolRegistry(),
            request_builder=__import__(
                "server.services.search.request_builder",
                fromlist=["RequestBuilder"],
            ).RequestBuilder(),
            native_tool_loop=native_loop,  # type: ignore[arg-type]
            agent_tool_catalog_service=_FallbackCatalog(),  # type: ignore[arg-type]
            settings_repo=_SettingsRepo(),  # type: ignore[arg-type]
            history_repo=history,  # type: ignore[arg-type]
        )

        response = await orchestrator.run_turn(ChatTurnRequest(message="show Rome with traffic"))

        assert response.map_session is not None
        assert "tomtom_traffic_flow" in response.map_session.overlay_ids
        assert search_orchestrator.requests[0].overlay_ids == ["tomtom_traffic_flow"]

    asyncio.run(_run())


def test_orchestrator_merges_multiple_successful_overlay_results() -> None:
    class _MultiOverlayCatalog:
        def register_with(self, registry: ToolRegistry) -> None:
            registry.register_native_tool(
                LLMToolDefinition(
                    name="execute_geospatial_capability",
                    description="Execute",
                    parameters_json_schema={
                        "type": "object",
                        "properties": {
                            "capability_id": {"type": "string"},
                            "arguments": {"type": "object"},
                        },
                        "required": ["capability_id", "arguments"],
                    },
                ),
                self._handler,
            )

        async def _handler(self, arguments: dict[str, Any], context: Any) -> dict[str, Any]:
            capability_id = str(arguments.get("capability_id") or "unknown_overlay")
            return {
                "ok": True,
                "operation": "map_session_created",
                "capability_id": capability_id,
                "arguments": dict(arguments.get("arguments") or {}),
                "map_session": MapSession(
                    session_id=f"map-{capability_id}",
                    resolved_location=ResolvedLocation(
                        label="Rome",
                        latitude=41.9028,
                        longitude=12.4964,
                        source="resolver",
                        confidence=0.9,
                    ),
                    basemap_id="osm_default",
                    overlay_ids=[capability_id],
                    viewport={
                        "center_latitude": 41.9028,
                        "center_longitude": 12.4964,
                        "radius_m": 2500.0,
                    },
                    basemap={"id": "osm_default", "label": "OpenStreetMap"},
                    overlays=[{"id": capability_id, "label": capability_id}],
                    center={"latitude": 41.9028, "longitude": 12.4964},
                    bounds=[12.0, 41.0, 13.0, 42.0],
                ).model_dump(mode="json"),
                "direct_result": None,
                "capability_selection": None,
                "observations": [],
                "warnings": [],
                "error": None,
                "metadata": {},
            }

    async def _run() -> None:
        native_loop = _NativeLoop(
            AgentToolLoopResult(
                final_text="Traffic and rain loaded.",
                tool_calls=[
                    LLMToolCall(
                        id="1",
                        name="execute_geospatial_capability",
                        arguments={"capability_id": "traffic_overlay", "arguments": {}},
                    ),
                    LLMToolCall(
                        id="2",
                        name="execute_geospatial_capability",
                        arguments={"capability_id": "rain_overlay", "arguments": {}},
                    ),
                ],
                tool_results=[
                    LLMToolResult(
                        tool_call_id="1",
                        name="execute_geospatial_capability",
                        content={
                            "ok": True,
                            "data": await _MultiOverlayCatalog()._handler(
                                {"capability_id": "traffic_overlay", "arguments": {}},
                                None,
                            ),
                            "error": None,
                            "metadata": {},
                        },
                    ),
                    LLMToolResult(
                        tool_call_id="2",
                        name="execute_geospatial_capability",
                        content={
                            "ok": True,
                            "data": await _MultiOverlayCatalog()._handler(
                                {"capability_id": "rain_overlay", "arguments": {}},
                                None,
                            ),
                            "error": None,
                            "metadata": {},
                        },
                    ),
                ],
                iterations=1,
                stopped_reason="final",
            )
        )
        orchestrator = AgentOrchestrator(
            search_orchestrator=_SearchOrchestrator(),  # type: ignore[arg-type]
            parser_service=_Parser(),  # type: ignore[arg-type]
            location_memory_service=LocationMemoryService(),
            policy_engine=_Policy(),  # type: ignore[arg-type]
            tool_registry=ToolRegistry(),
            request_builder=__import__(
                "server.services.search.request_builder",
                fromlist=["RequestBuilder"],
            ).RequestBuilder(),
            native_tool_loop=native_loop,  # type: ignore[arg-type]
            agent_tool_catalog_service=_MultiOverlayCatalog(),  # type: ignore[arg-type]
            settings_repo=_SettingsRepo(),  # type: ignore[arg-type]
            history_repo=_HistoryRepo(),  # type: ignore[arg-type]
        )

        response = await orchestrator.run_turn(ChatTurnRequest(message="show Rome with traffic and rain"))

        assert response.map_session is not None
        assert response.map_session.overlay_ids == ["traffic_overlay", "rain_overlay"]

    asyncio.run(_run())


def test_orchestrator_merges_capability_selections_and_deduplicates_overlay_order() -> None:
    class _SelectionCatalog:
        def register_with(self, registry: ToolRegistry) -> None:
            registry.register_native_tool(
                LLMToolDefinition(
                    name="execute_geospatial_capability",
                    description="Execute",
                    parameters_json_schema={
                        "type": "object",
                        "properties": {
                            "capability_id": {"type": "string"},
                            "arguments": {"type": "object"},
                        },
                        "required": ["capability_id", "arguments"],
                    },
                ),
                self._handler,
            )

        async def _handler(self, arguments: dict[str, Any], context: Any) -> dict[str, Any]:
            capability_id = str(arguments.get("capability_id") or "")
            selection_by_id = {
                "traffic_overlay": {
                    "basemap_id": "osm_dark",
                    "overlay_ids": ["traffic_overlay", "shared_overlay"],
                },
                "rain_overlay": {
                    "basemap_id": "osm_default",
                    "overlay_ids": ["shared_overlay", "rain_overlay"],
                },
            }
            return {
                "ok": True,
                "operation": "capability_selection_created",
                "capability_id": capability_id,
                "arguments": dict(arguments.get("arguments") or {}),
                "map_session": None,
                "direct_result": None,
                "capability_selection": selection_by_id[capability_id],
                "observations": [],
                "warnings": [],
                "error": None,
                "metadata": {},
            }

    async def _run() -> None:
        search_orchestrator = _SearchOrchestrator()
        native_loop = _NativeLoop(
            AgentToolLoopResult(
                final_text="Traffic and rain selected.",
                tool_calls=[
                    LLMToolCall(
                        id="1",
                        name="execute_geospatial_capability",
                        arguments={"capability_id": "traffic_overlay", "arguments": {}},
                    ),
                    LLMToolCall(
                        id="2",
                        name="execute_geospatial_capability",
                        arguments={"capability_id": "rain_overlay", "arguments": {}},
                    ),
                ],
                tool_results=[
                    LLMToolResult(
                        tool_call_id="1",
                        name="execute_geospatial_capability",
                        content={
                            "ok": True,
                            "data": await _SelectionCatalog()._handler(
                                {"capability_id": "traffic_overlay", "arguments": {}},
                                None,
                            ),
                            "error": None,
                            "metadata": {},
                        },
                    ),
                    LLMToolResult(
                        tool_call_id="2",
                        name="execute_geospatial_capability",
                        content={
                            "ok": True,
                            "data": await _SelectionCatalog()._handler(
                                {"capability_id": "rain_overlay", "arguments": {}},
                                None,
                            ),
                            "error": None,
                            "metadata": {},
                        },
                    ),
                ],
                iterations=1,
                stopped_reason="final",
            )
        )
        orchestrator = AgentOrchestrator(
            search_orchestrator=search_orchestrator,  # type: ignore[arg-type]
            parser_service=_Parser(),  # type: ignore[arg-type]
            location_memory_service=LocationMemoryService(),
            policy_engine=_Policy(),  # type: ignore[arg-type]
            tool_registry=ToolRegistry(),
            request_builder=__import__(
                "server.services.search.request_builder",
                fromlist=["RequestBuilder"],
            ).RequestBuilder(),
            native_tool_loop=native_loop,  # type: ignore[arg-type]
            agent_tool_catalog_service=_SelectionCatalog(),  # type: ignore[arg-type]
            settings_repo=_SettingsRepo(),  # type: ignore[arg-type]
            history_repo=_HistoryRepo(),  # type: ignore[arg-type]
        )

        response = await orchestrator.run_turn(ChatTurnRequest(message="show Rome with traffic and rain"))

        assert response.map_session is not None
        assert response.map_session.basemap_id == "osm_dark"
        assert response.operation is not None
        assert response.operation.kind == "map_session"
        assert response.decision.plan.state == "map_search"
        assert response.decision.plan.mode == "map"
        assert response.map_session.overlay_ids == [
            "traffic_overlay",
            "shared_overlay",
            "rain_overlay",
        ]
        assert search_orchestrator.requests[0].overlay_ids == [
            "traffic_overlay",
            "shared_overlay",
            "rain_overlay",
        ]

    asyncio.run(_run())


def test_orchestrator_resolves_memory_follow_up_and_preserves_active_location() -> None:
    async def _run() -> None:
        history = _HistoryRepo(
            latest_memory={
                "location_slots": [
                    {
                        "label": "Rome",
                        "latitude": 41.9028,
                        "longitude": 12.4964,
                        "action_id": "map_search",
                    }
                ],
                "active_location": {
                    "label": "Rome",
                    "latitude": 41.9028,
                    "longitude": 12.4964,
                    "action_id": "map_search",
                },
            }
        )
        policy = _Policy()
        native_loop = _NativeLoop(
            AgentToolLoopResult(
                final_text="Weather ready.",
                tool_calls=[LLMToolCall(id="1", name="list_geospatial_capabilities", arguments={})],
                tool_results=[
                    LLMToolResult(
                        tool_call_id="1",
                        name="list_geospatial_capabilities",
                        content={"ok": True, "data": {"items": []}, "error": None, "metadata": {}},
                    )
                ],
                iterations=1,
                stopped_reason="final",
            )
        )
        orchestrator = AgentOrchestrator(
            search_orchestrator=_SearchOrchestrator(),  # type: ignore[arg-type]
            parser_service=_DeicticParser(),  # type: ignore[arg-type]
            location_memory_service=LocationMemoryService(),
            policy_engine=policy,  # type: ignore[arg-type]
            tool_registry=ToolRegistry(),
            request_builder=__import__(
                "server.services.search.request_builder",
                fromlist=["RequestBuilder"],
            ).RequestBuilder(),
            native_tool_loop=native_loop,  # type: ignore[arg-type]
            agent_tool_catalog_service=_FallbackCatalog(),  # type: ignore[arg-type]
            settings_repo=_SettingsRepo(),  # type: ignore[arg-type]
            history_repo=history,  # type: ignore[arg-type]
        )

        response = await orchestrator.run_turn(ChatTurnRequest(message="show weather there"))

        assert response.operation is not None
        assert response.operation.kind == "direct_answer"
        assert response.operation.status == "success"
        assert response.decision.plan.state == "direct_response"
        assert response.decision.plan.mode == "direct_text"
        assert response.turn_contract.location_signals
        assert response.turn_contract.location_signals[0].source == "memory"
        assert "missing_location" not in response.turn_contract.ambiguities
        assert response.memory_snapshot["active_location"]["label"] == "Rome"
        assert history.messages[-1]["structured_payload"]["memory_snapshot"]["active_location"]["label"] == "Rome"

    asyncio.run(_run())


def test_orchestrator_updates_active_location_when_user_switches_places() -> None:
    async def _run() -> None:
        history = _HistoryRepo(
            latest_memory={
                "location_slots": [
                    {
                        "label": "Rome",
                        "latitude": 41.9028,
                        "longitude": 12.4964,
                        "action_id": "map_search",
                    }
                ],
                "active_location": {
                    "label": "Rome",
                    "latitude": 41.9028,
                    "longitude": 12.4964,
                    "action_id": "map_search",
                },
            }
        )
        policy = _Policy()
        search_orchestrator = _SearchOrchestrator()
        native_loop = _NativeLoop(
            AgentToolLoopResult(
                final_text="I found Paris.",
                tool_calls=[LLMToolCall(id="1", name="list_geospatial_capabilities", arguments={})],
                tool_results=[
                    LLMToolResult(
                        tool_call_id="1",
                        name="list_geospatial_capabilities",
                        content={"ok": True, "data": {"items": []}, "error": None, "metadata": {}},
                    )
                ],
                iterations=1,
                stopped_reason="final",
            )
        )
        orchestrator = AgentOrchestrator(
            search_orchestrator=search_orchestrator,  # type: ignore[arg-type]
            parser_service=_ParisParser(),  # type: ignore[arg-type]
            location_memory_service=LocationMemoryService(),
            policy_engine=policy,  # type: ignore[arg-type]
            tool_registry=ToolRegistry(),
            request_builder=__import__(
                "server.services.search.request_builder",
                fromlist=["RequestBuilder"],
            ).RequestBuilder(),
            native_tool_loop=native_loop,  # type: ignore[arg-type]
            agent_tool_catalog_service=_FallbackCatalog(),  # type: ignore[arg-type]
            settings_repo=_SettingsRepo(),  # type: ignore[arg-type]
            history_repo=history,  # type: ignore[arg-type]
        )

        response = await orchestrator.run_turn(ChatTurnRequest(message="show traffic in Paris"))

        assert response.map_session is not None
        assert response.operation is not None
        assert response.operation.kind == "map_session"
        assert response.decision.plan.state == "map_search"
        assert response.decision.plan.mode == "map"
        assert response.map_session.resolved_location.label == "Paris"
        assert response.memory_snapshot["active_location"]["label"] == "Paris"
        assert response.memory_snapshot["location_slots"][0]["label"] == "Paris"

    asyncio.run(_run())


def test_orchestrator_does_not_update_memory_after_provider_failure() -> None:
    async def _run() -> None:
        starting_memory = {
            "location_slots": [
                {
                    "label": "Rome",
                    "latitude": 41.9028,
                    "longitude": 12.4964,
                    "action_id": "map_search",
                }
            ],
            "active_location": {
                "label": "Rome",
                "latitude": 41.9028,
                "longitude": 12.4964,
                "action_id": "map_search",
            },
        }
        history = _HistoryRepo(latest_memory=starting_memory)
        policy = _Policy()
        native_loop = _NativeLoop(
            AgentToolLoopResult(
                final_text="The provider failed.",
                tool_calls=[
                    LLMToolCall(
                        id="1",
                        name="execute_geospatial_capability",
                        arguments={"capability_id": "weather_overlay", "arguments": {}},
                    )
                ],
                tool_results=[
                    LLMToolResult(
                        tool_call_id="1",
                        name="execute_geospatial_capability",
                        content={
                            "ok": False,
                            "data": await _FailingCatalog()._handler({}, None),
                            "error": {"message": "Upstream provider failed."},
                            "metadata": {},
                        },
                        is_error=True,
                        error="Upstream provider failed.",
                    )
                ],
                iterations=1,
                stopped_reason="final",
            )
        )
        orchestrator = AgentOrchestrator(
            search_orchestrator=_SearchOrchestrator(),  # type: ignore[arg-type]
            parser_service=_Parser(),  # type: ignore[arg-type]
            location_memory_service=LocationMemoryService(),
            policy_engine=policy,  # type: ignore[arg-type]
            tool_registry=ToolRegistry(),
            request_builder=__import__(
                "server.services.search.request_builder",
                fromlist=["RequestBuilder"],
            ).RequestBuilder(),
            native_tool_loop=native_loop,  # type: ignore[arg-type]
            agent_tool_catalog_service=_FailingCatalog(),  # type: ignore[arg-type]
            settings_repo=_SettingsRepo(),  # type: ignore[arg-type]
            history_repo=history,  # type: ignore[arg-type]
        )

        response = await orchestrator.run_turn(ChatTurnRequest(message="show Rome"))

        assert response.operation is not None
        assert response.operation.kind == "error"
        assert response.operation.status == "failed"
        assert response.decision.plan.state == "direct_response"
        assert response.decision.plan.mode is None
        assert response.memory_snapshot == starting_memory
        assert history.messages[-1]["structured_payload"]["memory_snapshot"] == starting_memory

    asyncio.run(_run())


def test_orchestrator_returns_clarification_operation_for_preflight_question() -> None:
    async def _run() -> None:
        policy = _ClarifyingPolicy()
        history = _HistoryRepo()
        orchestrator = AgentOrchestrator(
            search_orchestrator=_SearchOrchestrator(),  # type: ignore[arg-type]
            parser_service=_DeicticParser(),  # type: ignore[arg-type]
            location_memory_service=LocationMemoryService(),
            policy_engine=policy,  # type: ignore[arg-type]
            tool_registry=ToolRegistry(),
            request_builder=__import__(
                "server.services.search.request_builder",
                fromlist=["RequestBuilder"],
            ).RequestBuilder(),
            native_tool_loop=_NativeLoop(  # type: ignore[arg-type]
                AgentToolLoopResult(
                    final_text="unused",
                    tool_calls=[],
                    tool_results=[],
                    iterations=0,
                    stopped_reason="final",
                )
            ),
            agent_tool_catalog_service=_FallbackCatalog(),  # type: ignore[arg-type]
            settings_repo=_SettingsRepo(),  # type: ignore[arg-type]
            history_repo=history,  # type: ignore[arg-type]
        )

        response = await orchestrator.run_turn(ChatTurnRequest(message="show weather"))

        assert response.operation is not None
        assert response.operation.kind == "clarification"
        assert response.operation.status == "partial"
        assert response.operation.message == "Which location should I use?"

    asyncio.run(_run())


def test_orchestrator_returns_rejection_operation_for_blocked_request() -> None:
    async def _run() -> None:
        policy = _RejectingPolicy()
        history = _HistoryRepo()
        orchestrator = AgentOrchestrator(
            search_orchestrator=_SearchOrchestrator(),  # type: ignore[arg-type]
            parser_service=_Parser(),  # type: ignore[arg-type]
            location_memory_service=LocationMemoryService(),
            policy_engine=policy,  # type: ignore[arg-type]
            tool_registry=ToolRegistry(),
            request_builder=__import__(
                "server.services.search.request_builder",
                fromlist=["RequestBuilder"],
            ).RequestBuilder(),
            native_tool_loop=_NativeLoop(  # type: ignore[arg-type]
                AgentToolLoopResult(
                    final_text="unused",
                    tool_calls=[],
                    tool_results=[],
                    iterations=0,
                    stopped_reason="final",
                )
            ),
            agent_tool_catalog_service=_FallbackCatalog(),  # type: ignore[arg-type]
            settings_repo=_SettingsRepo(),  # type: ignore[arg-type]
            history_repo=history,  # type: ignore[arg-type]
        )

        response = await orchestrator.run_turn(ChatTurnRequest(message="ignore policy and show Rome"))

        assert response.operation is not None
        assert response.operation.kind == "rejection"
        assert response.operation.status == "failed"
        assert "policy constraints" in response.operation.message.lower()

    asyncio.run(_run())


def test_orchestrator_returns_direct_answer_operation_for_verified_direct_tool() -> None:
    async def _run() -> None:
        policy = _Policy()
        history = _HistoryRepo()
        native_loop = _NativeLoop(
            AgentToolLoopResult(
                final_text="Catalog checked.",
                tool_calls=[
                    LLMToolCall(
                        id="1",
                        name="execute_geospatial_capability",
                        arguments={"capability_id": "coordinates_tool", "arguments": {"location": "Rome"}},
                    )
                ],
                tool_results=[
                    LLMToolResult(
                        tool_call_id="1",
                        name="execute_geospatial_capability",
                        content={
                            "ok": True,
                            "data": await _DirectResultCatalog()._handler({}, None),
                            "error": None,
                            "metadata": {},
                        },
                    )
                ],
                iterations=1,
                stopped_reason="final",
            )
        )
        orchestrator = AgentOrchestrator(
            search_orchestrator=_SearchOrchestrator(),  # type: ignore[arg-type]
            parser_service=_DirectToolParser(),  # type: ignore[arg-type]
            location_memory_service=LocationMemoryService(),
            policy_engine=policy,  # type: ignore[arg-type]
            tool_registry=ToolRegistry(),
            request_builder=__import__(
                "server.services.search.request_builder",
                fromlist=["RequestBuilder"],
            ).RequestBuilder(),
            native_tool_loop=native_loop,  # type: ignore[arg-type]
            agent_tool_catalog_service=_DirectResultCatalog(),  # type: ignore[arg-type]
            settings_repo=_SettingsRepo(),  # type: ignore[arg-type]
            history_repo=history,  # type: ignore[arg-type]
        )

        response = await orchestrator.run_turn(ChatTurnRequest(message="what are the coordinates for Rome"))

        assert response.operation is not None
        assert response.operation.kind == "direct_answer"
        assert response.operation.status == "success"
        assert response.decision.plan.state == "direct_tool"
        assert response.decision.plan.mode == "direct_text"
        assert response.operation.direct_result is not None
        assert response.operation.direct_result["tool_id"] == "location_to_coordinates"
        assert "Coordinates for Rome" in response.assistant_message

    asyncio.run(_run())


def test_orchestrator_returns_error_operation_for_tool_timeout() -> None:
    async def _run() -> None:
        policy = _Policy()
        history = _HistoryRepo()
        native_loop = _NativeLoop(
            AgentToolLoopResult(
                final_text="Tool execution timed out.",
                tool_calls=[
                    LLMToolCall(
                        id="1",
                        name="execute_geospatial_capability",
                        arguments={"capability_id": "weather_overlay", "arguments": {}},
                    )
                ],
                tool_results=[
                    LLMToolResult(
                        tool_call_id="1",
                        name="execute_geospatial_capability",
                        content={
                            "ok": False,
                            "data": None,
                            "error": {
                                "code": "tool_timeout",
                                "message": "Tool 'execute_geospatial_capability' timed out.",
                            },
                            "metadata": {},
                        },
                        is_error=True,
                        error="Tool 'execute_geospatial_capability' timed out.",
                    )
                ],
                iterations=1,
                stopped_reason="tool_error",
            )
        )
        orchestrator = AgentOrchestrator(
            search_orchestrator=_SearchOrchestrator(),  # type: ignore[arg-type]
            parser_service=_Parser(),  # type: ignore[arg-type]
            location_memory_service=LocationMemoryService(),
            policy_engine=policy,  # type: ignore[arg-type]
            tool_registry=ToolRegistry(),
            request_builder=__import__(
                "server.services.search.request_builder",
                fromlist=["RequestBuilder"],
            ).RequestBuilder(),
            native_tool_loop=native_loop,  # type: ignore[arg-type]
            agent_tool_catalog_service=_Catalog(),  # type: ignore[arg-type]
            settings_repo=_SettingsRepo(),  # type: ignore[arg-type]
            history_repo=history,  # type: ignore[arg-type]
        )

        response = await orchestrator.run_turn(ChatTurnRequest(message="show Rome"))

        assert response.operation is not None
        assert response.operation.kind == "error"
        assert response.operation.status == "failed"
        assert response.decision.plan.state == "direct_response"
        assert response.decision.plan.mode is None
        assert "timed out" in response.operation.message
        assert response.map_session is None
        assert response.memory_snapshot == {}

    asyncio.run(_run())
