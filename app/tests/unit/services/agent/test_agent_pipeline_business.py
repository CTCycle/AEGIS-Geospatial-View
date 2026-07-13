from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from server.domain.agent.decision import ResolvedLocation
from server.domain.agent.execution import AgentExecutionContext
from server.domain.agent.extraction_schemas import LLMParserExtraction
from server.domain.agent.pipeline import (
    TaskFailureDetail,
    ToolPlan,
    ToolPlanStep,
)
from server.domain.chat import ChatTurnRequest
from server.domain.extraction.models import (
    ConversationContextSnapshot,
    LocationSignal,
    NormalizedAction,
    TurnParseResult,
    ViewportIntent,
)
from server.domain.geographics import MapSession
from server.services.agent.agent_tool_catalog_service import AgentToolCatalogService
from server.services.agent.conversation_state import ConversationTaskStateService
from server.services.agent.location_memory import LocationMemoryService
from server.services.agent.orchestrator import AgentOrchestrator
from server.services.agent.parser_service import ParserService
from server.services.agent.policy_engine import PolicyEngine
from server.services.agent.tool_plan_executor import ToolPlanExecutor
from server.services.agent.tool_planner import DeterministicToolPlanner
from server.services.agent.tool_registry import ToolRegistry
from server.services.geospatial.capability_registry import CapabilityRegistry
from server.services.geospatial.runtime_registry import RuntimeRegistry
from server.services.llm.types import LLMToolDefinition
from server.services.search.request_builder import RequestBuilder

###############################################################################
def _turn(
    text: str,
    *,
    relationship: str = "new_task",
    task_class: str = "map_search",
    requested_layers: list[str] | None = None,
    requested_basemap: str | None = None,
    entity_target: str | None = None,
    ambiguities: list[str] | None = None,
    clarification_plan: dict[str, Any] | None = None,
    viewport_intent: ViewportIntent | None = None,
) -> TurnParseResult:
    return TurnParseResult(
        user_text=text,
        conversation_context=ConversationContextSnapshot(
            recent_messages=[],
            memory_snapshot={},
        ),
        task_class=task_class,
        location_signals=[
            LocationSignal(
                signal_type="address",
                raw_value="Colosseum in Rome",
                normalized_value="Colosseum, Rome",
                latitude=41.8902,
                longitude=12.4922,
                confidence=0.99,
            )
        ]
        if task_class != "general_question"
        else [],
        normalized_action=NormalizedAction(
            action_id="data_layer_query" if requested_layers else "map_search",
            action_label="Residential building visualization"
            if requested_layers
            else "Map search",
            task_tags=["map"],
            action_tags=["housing"] if requested_layers else [],
            requires_location=task_class != "general_question",
        ),
        ambiguities=ambiguities or [],
        parser_confidence=0.95,
        relationship=relationship,
        entity_target=entity_target,
        requested_layers=requested_layers or [],
        requested_basemap=requested_basemap,
        tools_needed=bool(requested_layers),
        clarification_plan=clarification_plan,
        viewport_intent=viewport_intent,
    )

###############################################################################
class _SequenceParser:
    last_context_usage = None

    # -------------------------------------------------------------------------
    def __init__(self, turns: list[TurnParseResult]) -> None:
        self.turns = turns

    # -------------------------------------------------------------------------
    def parse_turn(self, user_message, memory_snapshot, conversation_messages):  # noqa: ANN001
        turn = self.turns.pop(0)
        return turn.model_copy(
            update={
                "user_text": user_message,
                "conversation_context": ConversationContextSnapshot(
                    recent_messages=[],
                    memory_snapshot=memory_snapshot,
                ),
            }
        )

###############################################################################
class _Resolver:

    # -------------------------------------------------------------------------
    async def resolve_location_signals(self, signals, memory):  # noqa: ANN001
        if signals:
            signal = signals[0]
            return ResolvedLocation(
                label=signal.normalized_value or signal.raw_value,
                latitude=float(signal.latitude or 41.8902),
                longitude=float(signal.longitude or 12.4922),
                source=signal.source,
                confidence=signal.confidence,
            )
        active = memory["active_location"]
        return ResolvedLocation.model_validate(active)

###############################################################################
class _Search:

    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        self.capability_registry = CapabilityRegistry()
        self.requests = []

    # -------------------------------------------------------------------------
    async def execute(self, request):  # noqa: ANN001
        self.requests.append(request)
        return MapSession(
            session_id=f"map-{len(self.requests)}",
            resolved_location=request.resolved_location,
            basemap_id=request.basemap_id,
            overlay_ids=list(request.overlay_ids),
            viewport=request.viewport,
            basemap={"id": request.basemap_id, "label": request.basemap_id},
            overlays=[
                {
                    "id": layer_id,
                    "label": layer_id,
                    "provider": "overpass",
                    "type": "geojson",
                    "rendering_mode": "geojson",
                    "url": f"/api/geospatial/layers/{layer_id}/geojson",
                }
                for layer_id in request.overlay_ids
            ],
        )

###############################################################################
@dataclass
class _Session:
    id: int = 1

###############################################################################
class _History:

    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    # -------------------------------------------------------------------------
    def upsert_session(self, session_id, title=None):  # noqa: ANN001
        return _Session(session_id or 1)

    # -------------------------------------------------------------------------
    def append_message(self, **kwargs):  # noqa: ANN003
        self.messages.append(kwargs)

    # -------------------------------------------------------------------------
    def list_recent_messages(self, session_id, limit):  # noqa: ANN001
        return []

    # -------------------------------------------------------------------------
    def get_latest_turn_contract(self, session_id):  # noqa: ANN001
        return None

    # -------------------------------------------------------------------------
    def get_latest_memory_snapshot(self, session_id):  # noqa: ANN001
        return {}

###############################################################################
@dataclass
class _Settings:
    agent_model_provider: str = "test"
    agent_model_name: str = "test"

###############################################################################
class _SettingsRepo:

    # -------------------------------------------------------------------------
    def get_or_create(self):
        return _Settings()

###############################################################################
class _ConversationRepository:

    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        self._state: dict[str, dict[str, object]] = {}

    # -------------------------------------------------------------------------
    def read_state(self, conversation_id: str) -> dict[str, object]:
        return self._state.setdefault(
            conversation_id,
            {"context_revision": 1, "active_instructions": [], "memory_snapshot": {}},
        )

    # -------------------------------------------------------------------------
    def write_state(self, conversation_id: str, **kwargs):
        current = self.read_state(conversation_id)
        current.update(kwargs)
        current["context_revision"] = int(current["context_revision"]) + 1
        return current["context_revision"]

###############################################################################
def _orchestrator(turns: list[TurnParseResult]) -> AgentOrchestrator:
    search = _Search()
    registry = ToolRegistry(runtime_registry=RuntimeRegistry())
    resolver = _Resolver()
    policy = PolicyEngine(
        location_resolver=resolver,  # type: ignore[arg-type]
        capability_registry=search.capability_registry,
        runtime_registry=RuntimeRegistry(),
    )
    request_builder = RequestBuilder()
    catalog = AgentToolCatalogService(
        capability_registry=search.capability_registry,
        runtime_registry=RuntimeRegistry(),
        search_orchestrator=search,  # type: ignore[arg-type]
        request_builder=request_builder,
        location_resolver=resolver,  # type: ignore[arg-type]
        tool_registry=registry,
        policy_engine=policy,
    )
    return AgentOrchestrator(
        search_orchestrator=search,  # type: ignore[arg-type]
        parser_service=_SequenceParser(turns),  # type: ignore[arg-type]
        location_memory_service=LocationMemoryService(),
        policy_engine=policy,
        tool_registry=registry,
        request_builder=request_builder,
        agent_tool_catalog_service=catalog,
        settings_repo=_SettingsRepo(),  # type: ignore[arg-type]
        history_repo=_History(),  # type: ignore[arg-type]
        task_state_service=ConversationTaskStateService(),
        conversation_repository=_ConversationRepository(),  # type: ignore[arg-type]
    )

###############################################################################
def test_houses_rule_selects_residential_buildings_and_not_amenities() -> None:
    extracted = ParserService._apply_domain_rules(
        "Show houses around the Coliseum in Rome, satellite view please.",
        LLMParserExtraction(),
        {},
    )
    assert extracted.requested_layers == ["overpass_residential_buildings"]
    assert "amenit" not in " ".join(extracted.requested_layers).lower()
    assert extracted.requested_basemap == "esri_world_imagery"
    assert extracted.entity_target == "residential_buildings"

###############################################################################
def test_colosseum_houses_and_street_temperature_follow_up_preserve_context() -> None:
    async def _run() -> None:
        orchestrator = _orchestrator(
            [
                _turn(
                    "houses",
                    requested_layers=["overpass_residential_buildings"],
                    requested_basemap="esri_world_imagery",
                    entity_target="residential_buildings",
                ),
                _turn(
                    "follow-up",
                    relationship="follow_up",
                    requested_basemap="osm_default",
                    viewport_intent=ViewportIntent(scope="preserve_current"),
                    ambiguities=["temperature_metric_underspecified"],
                    clarification_plan={
                        "question": "Which temperature metric should I use?",
                        "reason": "Temperature metric is ambiguous.",
                        "blocking_fields": ["temperature_metric"],
                        "options": [],
                        "preserve_valid_results": True,
                        "apply_visualization_changes": True,
                    },
                ),
            ]
        )
        first = await orchestrator.run_turn(
            ChatTurnRequest(
                message="Show houses around the Colosseum in Rome, satellite view please.",
                conversation_id="conv-test",
            )
        )
        assert first.map_session is not None
        assert first.map_session.basemap_id == "esri_world_imagery"
        assert first.map_session.overlay_ids == ["overpass_residential_buildings"]
        assert first.tool_plan is not None
        assert first.tool_plan.selected_tools == ["execute_geospatial_capability"]

        second = await orchestrator.run_turn(
            ChatTurnRequest(
                message="Street maps only and show medium temperature at the ground.",
                conversation_id="conv-test",
            )
        )
        assert second.operation is not None
        assert second.operation.kind == "clarification"
        assert second.operation.status == "partial"
        assert second.map_session is not None
        assert second.map_session.resolved_location.label == "Colosseum, Rome"
        assert second.map_session.basemap_id == "osm_default"
        assert second.map_session.overlay_ids == ["overpass_residential_buildings"]
        assert second.map_session.viewport.radius_m == first.map_session.viewport.radius_m
        assert "Which temperature metric should I use?" in second.assistant_message

    asyncio.run(_run())

###############################################################################
def test_follow_up_zoom_refinement_tightens_existing_viewport() -> None:
    async def _run() -> None:
        orchestrator = _orchestrator(
            [
                _turn(
                    "satellite",
                    requested_basemap="esri_world_imagery",
                    viewport_intent=ViewportIntent(scope="street"),
                ),
                _turn(
                    "closer",
                    relationship="follow_up",
                    viewport_intent=ViewportIntent(
                        scope="street",
                        tighten_relative_to_active=True,
                    ),
                ),
            ]
        )
        first = await orchestrator.run_turn(
            ChatTurnRequest(
                message="Show me satellite view around Via Pisa",
                conversation_id="conv-tighten",
            )
        )
        second = await orchestrator.run_turn(
            ChatTurnRequest(
                message="I want to see much more closely",
                conversation_id="conv-tighten",
            )
        )
        assert first.map_session is not None
        assert second.map_session is not None
        assert second.map_session.resolved_location.label == first.map_session.resolved_location.label
        assert second.map_session.viewport.radius_m < first.map_session.viewport.radius_m

    asyncio.run(_run())

###############################################################################
def test_failure_inquiry_uses_structured_failure_without_tools() -> None:
    async def _run() -> None:
        orchestrator = _orchestrator(
            [_turn("why", relationship="failure_inquiry", task_class="general_question")]
        )
        state = orchestrator.task_state_service
        failed = state.start_task(
            "conv-failure",
            _turn("failed"),
            "map_layers",
        )
        state.update_task(
            "conv-failure",
            failed.task_id,
            status="failed",
            failure=TaskFailureDetail(
                stage="tool_execution",
                tool_name="execute_geospatial_capability",
                sanitized_error="Overpass timed out.",
                recovery_suggestion="Retry with a smaller radius.",
                user_explanation="The building provider timed out.",
            ),
        )
        response = await orchestrator.run_turn(
            ChatTurnRequest(
                message="Why did the previous request fail?",
                conversation_id="conv-failure",
            )
        )
        assert response.operation is not None
        assert response.operation.kind == "failure_diagnostic"
        assert response.tool_payload is None
        assert "building provider timed out" in response.assistant_message.lower()

    asyncio.run(_run())

###############################################################################
def test_tool_planner_deduplicates_semantically_identical_calls() -> None:
    turn = _turn(
        "houses",
        requested_layers=[
            "overpass_residential_buildings",
            "overpass_residential_buildings",
        ],
    )
    plan = DeterministicToolPlanner().build_plan(turn, "geospatial_features")
    assert len(plan.steps) == 1

###############################################################################
def test_tool_plan_executor_orders_dependencies_and_retains_partial_success() -> None:
    async def _run() -> None:
        registry = ToolRegistry()
        order: list[str] = []

        async def handler(arguments, context):  # noqa: ANN001
            order.append(arguments["name"])
            if arguments["name"] == "optional":
                raise RuntimeError("optional failure")
            return {"name": arguments["name"]}

        definition = LLMToolDefinition(
            name="work",
            description="work",
            parameters_json_schema={
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        )
        registry.register_native_tool(definition, handler)
        plan = ToolPlan(
            tool_group="map_layers",
            selected_tools=["work"],
            candidate_tools=["work"],
            steps=[
                ToolPlanStep(
                    step_id="required",
                    tool_name="work",
                    reason="required",
                    arguments={"name": "required"},
                ),
                ToolPlanStep(
                    step_id="optional",
                    tool_name="work",
                    reason="optional",
                    arguments={"name": "optional"},
                    depends_on=["required"],
                    required=False,
                ),
            ],
        )
        results = await ToolPlanExecutor(tool_registry=registry).execute(
            plan,
            AgentExecutionContext(),
        )
        assert order == ["required", "optional"]
        assert results[0].ok is True
        assert results[1].ok is False

    asyncio.run(_run())

###############################################################################
def test_tool_output_validation_rejects_wrong_capability() -> None:
    async def _run() -> None:
        registry = ToolRegistry()

        async def handler(arguments, context):  # noqa: ANN001
            return {"ok": True, "capability_id": "wrong"}

        registry.register_native_tool(
            LLMToolDefinition(
                name="execute_geospatial_capability",
                description="execute",
                parameters_json_schema={
                    "type": "object",
                    "properties": {
                        "capability_id": {"type": "string"},
                        "arguments": {"type": "object"},
                    },
                    "required": ["capability_id", "arguments"],
                },
            ),
            handler,
        )
        plan = ToolPlan(
            tool_group="geospatial_features",
            candidate_tools=["execute_geospatial_capability"],
            selected_tools=["execute_geospatial_capability"],
            steps=[
                ToolPlanStep(
                    step_id="one",
                    tool_name="execute_geospatial_capability",
                    capability_id="expected",
                    reason="test",
                    arguments={"capability_id": "expected", "arguments": {}},
                )
            ],
        )
        result = (
            await ToolPlanExecutor(tool_registry=registry).execute(
                plan,
                AgentExecutionContext(),
            )
        )[0]
        assert result.ok is False
        assert result.error_code == "invalid_tool_output"

    asyncio.run(_run())
