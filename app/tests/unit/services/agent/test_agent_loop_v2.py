from __future__ import annotations

from collections import deque
import json
from typing import Any

import pytest
from pydantic import BaseModel

from server.domain.agent.context import AgentContextPackage
from server.domain.agent.capability_domains import CapabilityDomain
from server.domain.agent.capability_route import (
    AgentGoal,
    AgentPhase,
    AgentRunState,
    CapabilityRoute,
    CompletionContract,
    RenderObservation,
)
from server.domain.agent.decision import ResolvedLocation
from server.domain.agent.reliability import AgentExecutionBudget
from server.domain.agent.tool_result import ToolExecutionMetadata, ToolResult
from server.domain.agent.tools import RegisteredTool
from server.domain.llm.types import LLMResult, LLMToolCall, LLMToolDefinition
from server.services.agent.agent_loop import AgentLoop, AgentLoopRequest
from server.services.agent.capability_router import CapabilityRouter
from server.services.agent.tool_definitions import RouteRequestInput
from server.services.agent.tool_executor import ToolExecutor
from server.services.agent.tool_registry import ToolRegistry
from server.services.llm.errors import LLMProviderRequestError
from server.services.llm.transport import LLMTransportPolicy

###############################################################################
class FakeProvider:

    # -------------------------------------------------------------------------
    def __init__(self, results: list[LLMResult]) -> None:
        self.results = deque(results)
        self.requests: list[dict[str, Any]] = []

    # -------------------------------------------------------------------------
    async def achat(self, request: Any, **kwargs: Any) -> LLMResult:
        self.requests.append({"request": request, "kwargs": kwargs})
        return self.results.popleft()

###############################################################################
class FakeFactory:

    # -------------------------------------------------------------------------
    def __init__(self, provider: FakeProvider) -> None:
        self.provider = provider

    # -------------------------------------------------------------------------
    def get_provider(self, provider: str) -> FakeProvider:
        return self.provider

###############################################################################
class FakeCapabilityRegistry:

    # -------------------------------------------------------------------------
    def get_capability(self, capability_id: str) -> dict[str, object] | None:
        if capability_id == "places:hospitals":
            return {"id": capability_id, "provider": "overpass"}
        return None

    # -------------------------------------------------------------------------
    def shortlist(self, **kwargs: Any) -> list[dict[str, object]]:
        return [{"id": "places:hospitals"}]

###############################################################################
class FakeRuntimeRegistry:

    # -------------------------------------------------------------------------
    def is_enabled(self, capability_id: str) -> bool:
        return True

    # -------------------------------------------------------------------------
    def access_available(self, capability_id: str) -> bool:
        return True

###############################################################################
class EmptyInput(BaseModel):
    pass

###############################################################################
async def _answer_handler(arguments: BaseModel, state: AgentRunState) -> ToolResult:
    return ToolResult(
        call_id="handler-call",
        tool_name="test_tool",
        status="success",
        summary="tool completed",
        metadata=ToolExecutionMetadata(duration_ms=0),
    )

###############################################################################
def _loop(
    provider: FakeProvider,
    *,
    transport_policy: LLMTransportPolicy | None = None,
) -> AgentLoop:
    capability_registry = FakeCapabilityRegistry()
    registry = ToolRegistry(runtime_registry=FakeRuntimeRegistry())  # type: ignore[arg-type]
    registry.register(
        RegisteredTool(
            definition=LLMToolDefinition(
                name="route_request",
                description="test route",
                parameters_json_schema=RouteRequestInput.model_json_schema(),
            ),
            input_model=RouteRequestInput,
            handler=_answer_handler,
            domains=frozenset({CapabilityDomain.MIXED}),
            phases=frozenset({AgentPhase.ROUTE_REQUEST}),
            visibility="internal",
            prerequisites=frozenset(),
            timeout_key="tool_execution_seconds",
            idempotent=True,
            result_normalizer=lambda value, call_id: value.model_copy(
                update={"call_id": call_id}
            ),
        )
    )
    registry.register(
        RegisteredTool(
            definition=LLMToolDefinition(
                name="test_tool",
                description="test",
                parameters_json_schema={"type": "object"},
            ),
            input_model=EmptyInput,
            handler=_answer_handler,
            domains=frozenset({CapabilityDomain.MIXED}),
            phases=frozenset({AgentPhase.BUILD_TOOL_CONTEXT}),
            visibility="model",
            prerequisites=frozenset({"route"}),
            timeout_key="tool_execution_seconds",
            idempotent=True,
            result_normalizer=lambda value, call_id: value.model_copy(
                update={"call_id": call_id}
            ),
        )
    )
    return AgentLoop(
        provider_factory=FakeFactory(provider),  # type: ignore[arg-type]
        capability_router=CapabilityRouter(
            capability_registry=capability_registry,  # type: ignore[arg-type]
            runtime_registry=FakeRuntimeRegistry(),  # type: ignore[arg-type]
        ),
        tool_registry=registry,
        tool_executor=ToolExecutor(tool_registry=registry),
        transport_policy=transport_policy,
    )

###############################################################################
def _state() -> AgentRunState:
    return AgentRunState(
        request_id="request-1",
        conversation_id="conversation-1",
        phase=AgentPhase.RECEIVE_REQUEST,
        user_message="find hospitals",
    )

###############################################################################
def _route_call() -> LLMResult:
    return LLMResult(
        content="",
        tool_calls=[
            LLMToolCall(
                id="route-1",
                name="route_request",
                arguments={
                    "primary_domain": "data_retrieval",
                    "task_mode": "execute",
                    "presentation": "text",
                    "requires_location": False,
                    "capability_queries": ["hospitals"],
                },
            )
        ],
    )

###############################################################################
@pytest.mark.asyncio
async def test_loop_routes_exposes_tools_and_finishes_from_final_model_text() -> None:
    provider = FakeProvider(
        [
            _route_call(),
            LLMResult(content="Hospitals found."),
        ]
    )
    state = _state()
    outcome = await _loop(provider).run(
        AgentLoopRequest(
            provider="fake",
            model="fake-model",
            state=state,
            budget=AgentExecutionBudget(total_seconds=10, hard_max_seconds=10),
        )
    )

    assert outcome.stopped_reason == "goal_satisfied"
    assert outcome.final_text == "Hospitals found."
    assert [item["stage"] for item in outcome.state.budget_snapshot["stages"]] == [
        "route_request",
        "model_step",
    ]
    assert state.route is not None
    assert state.capability_ids == ["places:hospitals"]
    assert [item["kwargs"]["tool_choice"] for item in provider.requests] == [
        "required",
        "auto",
    ]
    assert provider.requests[0]["request"].provider_session_id == state.conversation_id
    assert state.transition_trace

###############################################################################
def test_native_route_promotes_the_execution_profile_once() -> None:
    simple_budget = AgentExecutionBudget(
        total_seconds=90,
        hard_max_seconds=300,
        simple_run_seconds=150,
    )
    complex_budget = AgentExecutionBudget(
        total_seconds=90,
        hard_max_seconds=300,
        simple_run_seconds=150,
    )
    simple_route = CapabilityRoute(
        primary_domain=CapabilityDomain.DATA_RETRIEVAL,
        task_mode="execute",
        presentation="text",
        requires_location=False,
        capability_queries=["weather"],
    )
    complex_route = simple_route.model_copy(
        update={"presentation": "map", "requires_location": True}
    )

    assert AgentLoop._budget_profile(simple_route) == "simple"  # pyright: ignore[reportPrivateUsage]
    assert AgentLoop._budget_profile(complex_route) == "complex"  # pyright: ignore[reportPrivateUsage]
    simple_budget.promote(AgentLoop._budget_profile(simple_route))  # pyright: ignore[reportPrivateUsage]
    complex_budget.promote(AgentLoop._budget_profile(complex_route))  # pyright: ignore[reportPrivateUsage]

    assert simple_budget.total_seconds == 150
    assert complex_budget.total_seconds == 300


###############################################################################
def test_verified_render_closes_map_completion_contract() -> None:
    state = _state()
    state.context_hydrated = True
    state.route = CapabilityRoute(
        primary_domain=CapabilityDomain.MAP_RENDERING,
        task_mode="execute",
        presentation="map",
        requires_location=True,
        capability_queries=["map"],
    )
    state.completion_contract = CompletionContract(
        operation="map",
        requirements=[],
        map_preparation_required=True,
        render_verification_required=True,
        render_verified=True,
    )
    state.render_verified = True
    state.render_observations = [
        RenderObservation(
            map_session_id="map-1",
            collection_revision=1,
            attempt=1,
            status="ready",
            checks={"viewport_valid": True},
            recovery="continue",
        )
    ]

    stop = _loop(FakeProvider([]))._evaluate_text_stop(  # pyright: ignore[reportPrivateUsage]
        state,
        state.route,
        "The map is ready.",
        available_tools=["apply_map_plan"],
    )

    assert stop == ("goal_satisfied", "The map is ready.")


###############################################################################
def test_render_recovery_exhaustion_preserves_first_failure_cause() -> None:
    state = _state()
    state.render_attempts = 2
    state.render_retry_exhausted = True
    state.render_observations = [
        RenderObservation(
            map_session_id="map-1",
            collection_revision=1,
            attempt=1,
            status="failed",
            checks={"required_sources_loaded": False},
            failure_code="missing_source",
            failure_stage="maplibre",
            failure_summary="The selected source was not registered.",
            recovery="revise_map",
        ),
        RenderObservation(
            map_session_id="map-2",
            collection_revision=2,
            attempt=2,
            status="failed",
            checks={"required_layers_present": False},
            failure_code="generic_validation",
            failure_stage="backend_validation",
            failure_summary="A later generic validation check failed.",
            recovery="terminal",
        ),
    ]
    loop = _loop(FakeProvider([]))
    outcome = loop._outcome(  # pyright: ignore[reportPrivateUsage]
        state,
        "The map renderer did not produce a verified result.",
        "render_recovery_exhausted",
        AgentLoopRequest(
            provider="fake",
            model="fake-model",
            state=state,
            budget=AgentExecutionBudget(total_seconds=10, hard_max_seconds=10),
        ),
    )

    assert "missing_source" in outcome.final_text
    assert "The selected source was not registered." in outcome.final_text
    assert "generic_validation" not in outcome.final_text


###############################################################################
def test_failed_render_requires_a_new_map_candidate_for_tool_progress() -> None:
    state = _state()
    state.route = CapabilityRoute(
        primary_domain=CapabilityDomain.MAP_RENDERING,
        task_mode="execute",
        presentation="map",
        requires_location=True,
        capability_queries=["map"],
    )
    state.render_observations = [
        RenderObservation(
            map_session_id="map-1",
            collection_revision=1,
            attempt=1,
            status="failed",
            checks={"required_sources_loaded": False},
            failure_code="missing_source",
            failure_stage="maplibre",
            failure_summary="The selected source was not registered.",
            action_fingerprint="failed-map-action",
            recovery="revise_map",
        )
    ]
    discovery = ToolResult(
        call_id="discovery-1",
        tool_name="discover_geospatial_capabilities",
        status="success",
        summary="Discovery completed.",
        metadata=ToolExecutionMetadata(duration_ms=0),
    )
    failed_map = ToolResult(
        call_id="map-repeat-1",
        tool_name="apply_map_plan",
        status="failed",
        summary="The same map action was rejected.",
        metadata=ToolExecutionMetadata(duration_ms=0),
    )

    expected = (
        "no_progress",
        "Render recovery requires a materially different map action.",
    )
    assert AgentLoop._evaluate_stop(  # pyright: ignore[reportPrivateUsage]
        state,
        state.route,
        [discovery],
        max_consecutive_tool_failures=3,
        max_validation_corrections=2,
        max_discovery_attempts=2,
    ) == expected
    assert AgentLoop._evaluate_stop(  # pyright: ignore[reportPrivateUsage]
        state,
        state.route,
        [failed_map],
        max_consecutive_tool_failures=3,
        max_validation_corrections=2,
        max_discovery_attempts=2,
    ) == expected


###############################################################################
@pytest.mark.asyncio
async def test_tool_turn_no_progress_after_render_failure_gets_bounded_correction() -> None:
    provider = FakeProvider(
        [
            LLMResult(
                content="",
                tool_calls=[
                    LLMToolCall(id="tool-1", name="test_tool", arguments={})
                ],
            ),
            LLMResult(
                content="",
                tool_calls=[
                    LLMToolCall(id="tool-2", name="test_tool", arguments={})
                ],
            ),
        ]
    )
    state = _state()
    state.context_hydrated = True
    state.route = CapabilityRoute(
        primary_domain=CapabilityDomain.DATA_RETRIEVAL,
        task_mode="execute",
        presentation="map",
        requires_location=False,
        capability_queries=["map"],
    )
    state.render_observations = [
        RenderObservation(
            map_session_id="map-1",
            collection_revision=1,
            attempt=1,
            status="failed",
            checks={"required_sources_loaded": False},
            failure_code="missing_source",
            failure_stage="maplibre",
            failure_summary="The selected source was not registered.",
            action_fingerprint="failed-map-action",
            recovery="revise_map",
        )
    ]

    outcome = await _loop(provider).run(
        AgentLoopRequest(
            provider="fake",
            model="fake-model",
            state=state,
            budget=AgentExecutionBudget(total_seconds=10, hard_max_seconds=10),
            max_no_progress_corrections=1,
        )
    )
    assert outcome.stopped_reason == "no_progress"
    assert state.no_progress_corrections == 1
    assert [
        item["observation_type"]
        for item in state.relevant_tool_outcomes
        if isinstance(item, dict) and "observation_type" in item
    ] == ["failed_render_recovery"]
    assert provider.requests[1]["kwargs"]["tool_choice"] == "auto"


###############################################################################
@pytest.mark.asyncio
async def test_verified_render_emits_tools_disabled_finalization_trace() -> None:
    provider = FakeProvider([LLMResult(content="Verified map summary.")])
    events = []

    async def trace(event) -> None:  # noqa: ANN001
        events.append(event)

    request = AgentLoopRequest(
        provider="fake",
        model="fake-model",
        state=_state(),
        budget=AgentExecutionBudget(total_seconds=10, hard_max_seconds=10),
        trace_callback=trace,
    )
    answer = await _loop(provider)._finalize_verified_render(  # pyright: ignore[reportPrivateUsage]
        request,
        provider,
        [],
    )

    assert answer == "Verified map summary."
    finalization = [
        event
        for event in events
        if event.kind in {"finalization_started", "finalization_completed"}
    ]
    assert [event.kind for event in finalization] == [
        "finalization_started",
        "finalization_completed",
    ]
    assert all(event.payload["tools_exposed"] == 0 for event in finalization)
    assert all(event.payload["tool_choice"] == "none" for event in finalization)
    assert [event.payload["model_call_index"] for event in finalization] == [0, 1]
    assert set(finalization[0].payload) == {
        "reason",
        "tools_exposed",
        "tool_choice",
        "model_call_index",
    }
    assert set(finalization[1].payload) == {
        "reason",
        "tools_exposed",
        "tool_choice",
        "model_call_index",
        "outcome",
    }
    assert all(
        key not in event.payload
        for event in finalization
        for key in ("content", "messages", "tool_calls", "reasoning")
    )
    assert provider.requests[0]["kwargs"]["tool_choice"] == "none"
    assert provider.requests[0]["kwargs"]["tools"] is None

###############################################################################
def test_native_goal_compiles_deterministic_completion_contract() -> None:
    state = _state()
    route = CapabilityRoute(
        primary_domain=CapabilityDomain.DATA_RETRIEVAL,
        task_mode="execute",
        presentation="both",
        requires_location=True,
        capability_queries=["hospitals"],
        operation="filter",
        target_refs=["target-1"],
        temporal_scope={
            "mode": "historical",
            "start_time_iso": "2026-09-01T00:00:00+00:00",
            "end_time_iso": "2026-09-02T00:00:00+00:00",
            "granularity": "none",
            "aggregation": "none",
        },
        spatial_scope={
            "kind": "bbox",
            "relationship": "in",
            "target_refs": ["target-1"],
        },
        filters={"category": "hospital"},
    )

    AgentLoop._compile_native_goal(state, route)  # pyright: ignore[reportPrivateUsage]

    assert state.goal is not None
    assert state.goal.operation == "filter"
    assert state.goal.temporal_scope["mode"] == "historical"
    assert state.goal.spatial_scope[0]["kind"] == "bbox"
    assert state.goal.filters == {"category": "hospital"}
    assert state.completion_contract is not None
    assert state.completion_contract.requirements == [
        "location_resolved",
        "required_data_retrieved",
        "temporal_scope_applied",
        "spatial_scope_applied",
        "map_candidate_prepared",
    ]
    assert state.completion_contract.evidence_required is True
    assert state.completion_contract.map_preparation_required is True
    assert state.completion_contract.temporal_scope_required is True
    assert state.completion_contract.spatial_scope_required is True


###############################################################################
def test_map_add_route_requires_provider_data_when_data_retrieval_is_secondary() -> None:
    state = _state()
    route = CapabilityRoute(
        primary_domain=CapabilityDomain.MAP_RENDERING,
        secondary_domains=[CapabilityDomain.DATA_RETRIEVAL],
        task_mode="execute",
        presentation="map",
        requires_location=True,
        capability_queries=["earthquakes"],
        operation="add_layer",
        target_refs=["earthquakes", "Japan"],
        spatial_scope={
            "kind": "administrative_geometry",
            "relationship": "around",
            "target_refs": ["Japan"],
        },
    )

    AgentLoop._compile_native_goal(state, route)  # pyright: ignore[reportPrivateUsage]

    assert state.completion_contract is not None
    assert state.completion_contract.data_requirement == "provider_data"
    assert "required_data_retrieved" in state.completion_contract.requirements


###############################################################################
def test_text_geocode_resolution_satisfies_data_and_spatial_completion() -> None:
    state = _state()
    route = CapabilityRoute(
        primary_domain=CapabilityDomain.PLACE_SEARCH,
        task_mode="execute",
        presentation="text",
        requires_location=True,
        capability_queries=["geocode"],
        operation="geocode",
        target_refs=["Rome, Italy"],
        spatial_scope={
            "kind": "point",
            "relationship": "at",
            "target_refs": ["Rome, Italy"],
        },
    )
    state.route = route
    AgentLoop._compile_native_goal(state, route)  # pyright: ignore[reportPrivateUsage]
    state.context_hydrated = True
    state.location_refs["rome, italy"] = ResolvedLocation(
        label="Rome, Italy",
        latitude=41.9028,
        longitude=12.4964,
        confidence=0.95,
        location_type="city",
    )
    state.tool_results.append(
        ToolResult(
            call_id="resolve-rome",
            tool_name="resolve_geospatial_location",
            status="success",
            summary="Resolved Rome, Italy.",
            data={
                "target_id": "rome, italy",
                "coordinates": [12.4964, 41.9028],
            },
            metadata=ToolExecutionMetadata(duration_ms=0),
        )
    )

    checks = AgentLoop._completion_checks(state)  # pyright: ignore[reportPrivateUsage]

    assert checks["required_data_retrieved"] is True
    assert checks["spatial_scope_applied"] is True
    assert AgentLoop._pending_requirements_for_task_state(  # pyright: ignore[reportPrivateUsage]
        state
    ) == []


###############################################################################
def test_location_only_map_recovery_requires_a_single_resolved_location() -> None:
    state = _state()
    route = CapabilityRoute(
        primary_domain=CapabilityDomain.MAP_RENDERING,
        task_mode="execute",
        presentation="map",
        requires_location=True,
        capability_queries=["place search", "map viewport"],
    )
    AgentLoop._compile_native_goal(state, route)  # pyright: ignore[reportPrivateUsage]
    state.location_refs["great barrier reef, australia"] = ResolvedLocation(
        label="Great Barrier Reef, Australia",
        latitude=-16.35,
        longitude=145.9,
        confidence=0.87,
        location_type="reef",
    )
    assert AgentLoop._needs_location_only_map_recovery(  # pyright: ignore[reportPrivateUsage]
        state, route
    )

    state.location_refs["australia"] = state.location_refs[
        "great barrier reef, australia"
    ]
    assert not AgentLoop._needs_location_only_map_recovery(  # pyright: ignore[reportPrivateUsage]
        state, route
    )
    state.route = route
    state.tool_results.append(
        ToolResult(
            call_id="resolve-reef",
            tool_name="resolve_geospatial_location",
            status="success",
            summary="Resolved Great Barrier Reef, Australia.",
            data={"target_id": "great barrier reef, australia"},
            metadata=ToolExecutionMetadata(duration_ms=0),
        )
    )
    assert AgentLoop._completion_checks(state)["required_data_retrieved"] is False  # pyright: ignore[reportPrivateUsage]


###############################################################################
def test_location_only_map_recovery_accepts_duplicate_same_location_results() -> None:
    state = _state()
    route = CapabilityRoute(
        primary_domain=CapabilityDomain.MAP_RENDERING,
        task_mode="execute",
        presentation="map",
        requires_location=True,
        capability_queries=["place search", "map viewport"],
    )
    AgentLoop._compile_native_goal(state, route)  # pyright: ignore[reportPrivateUsage]
    state.location_refs["kilimanjaro, tanzania"] = ResolvedLocation(
        label="Kilimanjaro, Tanzania",
        latitude=-3.0786,
        longitude=37.4198,
        confidence=0.81,
        location_type="massif",
    )
    for call_id in ("resolve-1", "resolve-2"):
        state.tool_results.append(
            ToolResult(
                call_id=call_id,
                tool_name="resolve_geospatial_location",
                status="success",
                summary="Resolved Kilimanjaro, Tanzania.",
                data={"target_id": "Kilimanjaro, Tanzania"},
                metadata=ToolExecutionMetadata(duration_ms=0),
            )
        )

    assert AgentLoop._location_only_map_recovery_ref(state, route) == (
        "kilimanjaro, tanzania"
    )  # pyright: ignore[reportPrivateUsage]
    assert AgentLoop._needs_location_only_map_recovery(  # pyright: ignore[reportPrivateUsage]
        state, route
    )


###############################################################################
@pytest.mark.asyncio
async def test_location_only_map_recovery_replaces_stale_failure_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = FakeProvider([LLMResult(content="The map cannot be prepared.")])
    loop = _loop(provider)
    route = CapabilityRoute(
        primary_domain=CapabilityDomain.MAP_RENDERING,
        task_mode="execute",
        presentation="map",
        requires_location=True,
        capability_queries=["basemap", "location map view"],
    )
    state = _state()
    state.context_hydrated = True
    state.route = route
    state.location_refs["great barrier reef, australia"] = ResolvedLocation(
        label="Great Barrier Reef, Australia",
        latitude=-16.35,
        longitude=145.9,
        confidence=0.87,
        location_type="reef",
    )
    state.tool_results.append(
        ToolResult(
            call_id="resolve-current",
            tool_name="resolve_geospatial_location",
            status="success",
            summary="Resolved Great Barrier Reef, Australia.",
            data={"target_id": "great barrier reef, australia"},
            metadata=ToolExecutionMetadata(duration_ms=0),
        )
    )

    async def recover_map(*args: Any) -> list[ToolResult]:
        state.prepared_map_session = object()  # type: ignore[assignment]
        return [
            ToolResult(
                call_id="apply-map",
                tool_name="apply_map_plan",
                status="success",
                summary="A map candidate was prepared.",
                metadata=ToolExecutionMetadata(duration_ms=0),
            )
        ]

    monkeypatch.setattr(loop, "_recover_location_only_map", recover_map)
    outcome = await loop.run(
        AgentLoopRequest(
            provider="fake",
            model="fake-model",
            state=state,
            budget=AgentExecutionBudget(total_seconds=10, hard_max_seconds=10),
        )
    )

    assert outcome.stopped_reason == "awaiting_render"
    assert outcome.final_text == "The map is ready."


###############################################################################
@pytest.mark.asyncio
async def test_location_only_map_recovery_runs_after_a_location_tool_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = FakeProvider(
        [
            LLMResult(
                content="",
                tool_calls=[
                    LLMToolCall(
                        id="lookup-1",
                        name="test_tool",
                        arguments={},
                    )
                ],
            )
        ]
    )
    loop = _loop(provider)
    state = _state()
    state.context_hydrated = True
    state.route = CapabilityRoute(
        primary_domain=CapabilityDomain.MAP_RENDERING,
        task_mode="execute",
        presentation="map",
        requires_location=True,
        capability_queries=["location map"],
    )
    state.location_refs["florence, tuscany, italy"] = ResolvedLocation(
        label="Florence, Tuscany, Italy",
        latitude=43.7698,
        longitude=11.2556,
        confidence=0.84,
        source="test",
    )
    state.completion_contract = CompletionContract(
        operation="map",
        requirements=["location_resolved", "map_candidate_prepared"],
        map_preparation_required=True,
        render_verification_required=True,
    )

    monkeypatch.setattr(
        loop.tool_registry,
        "expose",
        lambda _state: [
            LLMToolDefinition(
                name="test_tool",
                description="test",
                parameters_json_schema={"type": "object"},
            )
        ],
    )

    async def execute_tool(*args: Any, **kwargs: Any) -> list[ToolResult]:
        return [
            ToolResult(
                call_id="lookup-1",
                tool_name="test_tool",
                status="success",
                summary="location resolved",
                metadata=ToolExecutionMetadata(duration_ms=0),
            )
        ]

    monkeypatch.setattr(loop, "_execute_calls", execute_tool)

    async def recover_map(*args: Any, **kwargs: Any) -> list[ToolResult]:
        state.prepared_map_session = object()  # type: ignore[assignment]
        return [
            ToolResult(
                call_id="recovery-1",
                tool_name="apply_map_plan",
                status="success",
                summary="map candidate prepared",
                metadata=ToolExecutionMetadata(duration_ms=0),
            )
        ]

    monkeypatch.setattr(loop, "_recover_location_only_map", recover_map)
    outcome = await loop.run(
        AgentLoopRequest(
            provider="fake",
            model="fake-model",
            state=state,
            budget=AgentExecutionBudget(total_seconds=10, hard_max_seconds=10),
        )
    )

    assert outcome.stopped_reason == "awaiting_render", (
        outcome.final_text,
        outcome.failure_category,
        outcome.failure_detail,
    )
    assert outcome.state.prepared_map_session is not None

###############################################################################
def test_location_only_map_recovery_uses_the_current_location_result() -> None:
    state = _state()
    route = CapabilityRoute(
        primary_domain=CapabilityDomain.MAP_RENDERING,
        task_mode="execute",
        presentation="map",
        requires_location=True,
        capability_queries=["basemap", "map rendering"],
    )
    AgentLoop._compile_native_goal(state, route)  # pyright: ignore[reportPrivateUsage]
    state.location_refs["paris, france"] = ResolvedLocation(
        label="Paris, France",
        latitude=48.8566,
        longitude=2.3522,
        confidence=0.9,
        location_type="city",
    )
    state.location_refs["kolkata, india"] = ResolvedLocation(
        label="Kolkata, West Bengal, India",
        latitude=22.5726,
        longitude=88.3639,
        confidence=0.9,
        location_type="city",
    )
    state.tool_results.append(
        ToolResult(
            call_id="resolve-current",
            tool_name="resolve_geospatial_location",
            status="success",
            summary="Resolved Kolkata, West Bengal, India.",
            data={"target_id": "kolkata, india"},
            metadata=ToolExecutionMetadata(duration_ms=0),
        )
    )

    assert AgentLoop._needs_location_only_map_recovery(  # pyright: ignore[reportPrivateUsage]
        state, route
    )
    assert AgentLoop._location_only_map_recovery_ref(  # pyright: ignore[reportPrivateUsage]
        state
    ) == "kolkata, india"

###############################################################################
def test_location_only_map_recovery_can_reuse_one_close_current_route_ref() -> None:
    state = _state()
    route = CapabilityRoute(
        primary_domain=CapabilityDomain.MAP_RENDERING,
        task_mode="execute",
        presentation="map",
        requires_location=True,
        capability_queries=["geocode place name", "basemap"],
        target_refs=["Kolkatta, India"],
    )
    AgentLoop._compile_native_goal(state, route)  # pyright: ignore[reportPrivateUsage]
    state.location_refs["paris, france"] = ResolvedLocation(
        label="Paris, France",
        latitude=48.8566,
        longitude=2.3522,
        confidence=0.9,
        location_type="city",
    )
    state.location_refs["kolkata, india"] = ResolvedLocation(
        label="Kolkata, West Bengal, India",
        latitude=22.5726,
        longitude=88.3639,
        confidence=0.9,
        location_type="city",
    )

    assert AgentLoop._location_only_map_recovery_ref(  # pyright: ignore[reportPrivateUsage]
        state, route
    ) == "kolkata, india"

###############################################################################
@pytest.mark.asyncio
async def test_model_budget_exhaustion_has_a_distinct_terminal_reason() -> None:
    provider = FakeProvider([_route_call()])
    outcome = await _loop(provider).run(
        AgentLoopRequest(
            provider="fake",
            model="fake-model",
            state=_state(),
            budget=AgentExecutionBudget(total_seconds=10, hard_max_seconds=10),
            max_model_calls=1,
        )
    )

    assert outcome.stopped_reason == "model_budget_exhausted"
    assert outcome.state.termination_reason == "model_budget_exhausted"
    assert outcome.state.model_calls == 1
    assert outcome.state.transitions == 1

###############################################################################
@pytest.mark.asyncio
async def test_transition_budget_exhaustion_has_a_distinct_terminal_reason() -> None:
    provider = FakeProvider([_route_call()])
    outcome = await _loop(provider).run(
        AgentLoopRequest(
            provider="fake",
            model="fake-model",
            state=_state(),
            budget=AgentExecutionBudget(total_seconds=10, hard_max_seconds=10),
            max_state_transitions=1,
        )
    )

    assert outcome.stopped_reason == "transition_budget_exhausted"
    assert outcome.state.termination_reason == "transition_budget_exhausted"
    assert outcome.state.transitions == 1

###############################################################################
@pytest.mark.asyncio
async def test_opencode_go_native_calls_use_conversation_session_and_compatible_thinking_mode() -> None:
    provider = FakeProvider([LLMResult(content="ready")])
    loop = _loop(provider)
    state = _state()
    request = AgentLoopRequest(
        provider="opencode-go",
        model="deepseek-v4-flash",
        state=state,
        budget=AgentExecutionBudget(total_seconds=10, hard_max_seconds=10),
    )

    await loop._model_call(  # pyright: ignore[reportPrivateUsage]
        request,
        provider,  # type: ignore[arg-type]
        [],
        [],
        tool_choice="none",
    )

    captured = provider.requests[0]["request"]
    assert captured.provider_session_id == state.conversation_id
    assert captured.metadata["thinking_mode"] == "disabled"

###############################################################################
@pytest.mark.asyncio
async def test_model_retry_uses_same_provider_and_records_safe_transport_trace() -> None:

    ###############################################################################
    class _RetryingProvider(FakeProvider):
        provider_name = "opencode-go"
        base_url = "https://opencode.example/v1"

        # -------------------------------------------------------------------------
        def __init__(self) -> None:
            super().__init__([LLMResult(content="ready")])

        # -------------------------------------------------------------------------
        def protocol_for_model(self, _model: str) -> str:
            return "openai-chat-completions"

        # -------------------------------------------------------------------------
        async def achat(self, request: Any, **kwargs: Any) -> LLMResult:
            self.requests.append({"request": request, "kwargs": kwargs})
            if len(self.requests) == 1:
                raise LLMProviderRequestError(
                    provider="opencode-go",
                    model="deepseek-v4-flash",
                    stage="model_call",
                    code="provider_request_failed",
                    retryable=True,
                    diagnostics={"exception_type": "ConnectError"},
                )
            return self.results.popleft()

    provider = _RetryingProvider()
    request = AgentLoopRequest(
        provider="opencode-go",
        model="deepseek-v4-flash",
        state=_state(),
        budget=AgentExecutionBudget(total_seconds=10, hard_max_seconds=10),
    )

    result = await _loop(
        provider,
        transport_policy=LLMTransportPolicy(
            max_attempts=2,
            retry_backoff_base_seconds=0.0,
            retry_backoff_max_seconds=0.0,
        ),
    )._model_call(  # pyright: ignore[reportPrivateUsage]
        request,
        provider,
        [],
        [],
        tool_choice="none",
    )

    assert result.content == "ready"
    assert len(provider.requests) == 2
    failure = next(
        item for item in request.state.model_trace if item.get("status") == "failed"
    )
    assert failure["provider"] == "opencode-go"
    assert failure["model"] == "deepseek-v4-flash"
    assert failure["protocol"] == "openai-chat-completions"
    assert failure["endpoint_host"] == "opencode.example"
    assert failure["exception_class"] == "ConnectError"
    assert failure["retryable"] is True

###############################################################################
@pytest.mark.asyncio
async def test_native_model_context_usage_is_recorded_and_emitted() -> None:
    usage = {
        "estimated_input_tokens": 120,
        "reported_input_tokens": 110,
        "reported_output_tokens": 18,
        "model_context_limit": 4096,
        "compaction_applied": True,
    }
    provider = FakeProvider([LLMResult(content="ready", context_usage=usage)])
    budget = AgentExecutionBudget(total_seconds=10, hard_max_seconds=10)
    emitted: list[dict[str, Any]] = []
    request = AgentLoopRequest(
        provider="fake",
        model="fake-model",
        state=_state(),
        budget=budget,
        context_usage_callback=emitted.append,
    )

    await _loop(provider)._model_call(  # pyright: ignore[reportPrivateUsage]
        request,
        provider,  # type: ignore[arg-type]
        [],
        [],
        tool_choice="none",
    )

    assert emitted == [usage]
    assert budget.context_allocations == [
        {
            "phase": "native_loop",
            "model": "fake-model",
            "attempt": 1,
            "model_call": 1,
        **usage,
        }
    ]
    assert request.state.context_usage_trace[0]["reported_input_tokens"] == 110
    assert request.state.model_trace[0]["status"] == "observed"


###############################################################################
@pytest.mark.asyncio
async def test_run_control_stops_before_a_superseded_model_result_is_applied() -> None:
    provider = FakeProvider(
        [
            _route_call(),
            LLMResult(
                content="",
                tool_calls=[LLMToolCall(id="call-1", name="test_tool", arguments={})],
            ),
        ]
    )

    def check() -> str | None:
        return "superseded" if len(provider.requests) >= 2 else None

    outcome = await _loop(provider).run(
        AgentLoopRequest(
            provider="fake",
            model="fake-model",
            state=_state(),
            budget=AgentExecutionBudget(total_seconds=10, hard_max_seconds=10),
            run_state_check=check,
        )
    )

    assert outcome.stopped_reason == "superseded"
    assert outcome.state.tool_calls == 0
    assert outcome.state.termination_reason == "superseded"


###############################################################################
@pytest.mark.asyncio
async def test_run_control_stops_cancelled_request_before_provider_call() -> None:
    provider = FakeProvider([_route_call()])
    outcome = await _loop(provider).run(
        AgentLoopRequest(
            provider="fake",
            model="fake-model",
            state=_state(),
            budget=AgentExecutionBudget(total_seconds=10, hard_max_seconds=10),
            run_state_check=lambda: "cancelled",
        )
    )

    assert outcome.stopped_reason == "cancelled"
    assert provider.requests == []

###############################################################################
@pytest.mark.asyncio
async def test_loop_preserves_malformed_tool_call_as_failure() -> None:
    provider = FakeProvider(
        [
            _route_call(),
            LLMResult(
                content="",
                tool_calls=[
                    LLMToolCall(
                        id="call-1",
                        name="test_tool",
                        arguments=None,
                        parse_error="invalid_json",
                    )
                ],
            ),
        ]
    )
    outcome = await _loop(provider).run(
        AgentLoopRequest(
            provider="fake",
            model="fake-model",
            state=_state(),
            budget=AgentExecutionBudget(total_seconds=10, hard_max_seconds=10),
            max_iterations=1,
        )
    )

    assert outcome.tool_results[0].error is not None
    assert outcome.tool_results[0].error.error_type == "malformed_call"

###############################################################################
@pytest.mark.asyncio
async def test_successful_tool_is_followed_by_one_final_model_step() -> None:
    provider = FakeProvider(
        [
            _route_call(),
            LLMResult(
                content="",
                tool_calls=[
                    LLMToolCall(
                        id="call-1",
                        name="test_tool",
                        arguments={},
                    )
                ],
            ),
            LLMResult(content="The tool result is complete."),
        ]
    )
    outcome = await _loop(provider).run(
        AgentLoopRequest(
            provider="fake",
            model="fake-model",
            state=_state(),
            budget=AgentExecutionBudget(total_seconds=10, hard_max_seconds=10),
        )
    )

    assert outcome.stopped_reason == "goal_satisfied"
    assert outcome.final_text == "The tool result is complete."
    assert len(provider.requests) == 3
    assert outcome.state.tool_calls == 1
    assistant_message = provider.requests[2]["request"].messages[1]
    assert assistant_message["tool_calls"][0]["name"] == "test_tool"
    assert assistant_message["tool_calls"][0]["arguments"] == {}


###############################################################################
@pytest.mark.asyncio
async def test_weather_completion_has_bounded_fallback_when_model_budget_is_exhausted() -> None:
    provider = FakeProvider([])
    state = _state()
    state.tool_results.append(
        ToolResult(
            call_id="weather-1",
            tool_name="execute_geospatial_capability",
            status="success",
            summary="weather fetched",
            data={
                "capability_id": "get_weather_forecast",
                "observations": {
                    "temperature_2m": 27.3,
                    "relative_humidity_2m": 62,
                    "precipitation": 0.0,
                    "wind_speed_10m": 9.5,
                    "surface_pressure": 1010.0,
                    "weather_code": 3,
                },
                "observation_time": "2026-09-18T14:00",
                "timezone": "Europe/Rome",
                "query": {
                    "location_ref": "rome",
                    "resolved_location": "Rome, Italy",
                },
            },
            metadata=ToolExecutionMetadata(duration_ms=0),
        )
    )
    request = AgentLoopRequest(
        provider="fake",
        model="fake-model",
        state=state,
        budget=AgentExecutionBudget(total_seconds=10, hard_max_seconds=10),
        max_model_calls=1,
    )
    request.budget.configure_limits(max_model_calls=1)
    state.model_calls = 1

    answer = await _loop(provider)._finalize_completed_request(  # pyright: ignore[reportPrivateUsage]
        request,
        provider,
        [],
    )

    assert "Current weather for Rome, Italy" in answer
    assert "temperature 27.3°C" in answer
    assert "humidity 62%" in answer
    assert "Observation time: 2026-09-18T14:00 (Europe/Rome)" in answer

###############################################################################
@pytest.mark.asyncio
async def test_hydrated_context_is_rebuilt_with_the_latest_observation() -> None:
    provider = FakeProvider(
        [
            LLMResult(
                content="",
                tool_calls=[
                    LLMToolCall(
                        id="route-1",
                        name="route_request",
                        arguments={
                            "primary_domain": "map_rendering",
                            "task_mode": "execute",
                            "presentation": "text",
                            "requires_location": False,
                            "capability_queries": ["hospitals"],
                        },
                    )
                ],
            ),
            LLMResult(
                content="",
                tool_calls=[
                    LLMToolCall(id="call-1", name="test_tool", arguments={})
                ],
            ),
            LLMResult(content="The tool result is complete."),
        ]
    )
    state = _state()
    state.context_hydrated = True
    state.recent_messages = [
        {"role": "assistant", "content": "Earlier context."}
    ]
    state.task_state = {"task": "find hospitals"}
    package = AgentContextPackage(
        current_user_message=state.user_message,
        recent_messages=state.recent_messages,
        task_state=state.task_state,
    )
    state.active_directives = [
        {"directive_id": "d1", "normalized_text": "Use verified sources."}
    ]
    state.summary = {"turn_facts": [{"content": "Lugano"}]}

    outcome = await _loop(provider).run(
        AgentLoopRequest(
            provider="fake",
            model="fake-model",
            state=state,
            budget=AgentExecutionBudget(total_seconds=10, hard_max_seconds=10),
            messages=package.recent_messages,
        )
    )

    assert outcome.stopped_reason == "goal_satisfied"
    latest_request = provider.requests[2]["request"]
    canonical_context = next(
        message["content"]
        for message in latest_request.messages
        if "CANONICAL_NATIVE_CONTEXT" in message.get("content", "")
    )
    assert "tool completed" in canonical_context
    assert any(
        message.get("content") == "Earlier context."
        for message in latest_request.messages
    )

###############################################################################
def test_tool_observation_preserves_bounded_result_data() -> None:
    result = ToolResult(
        call_id="call-1",
        tool_name="discover_geospatial_capabilities",
        status="success",
        summary="Found 1 eligible capability.",
        data={
            "capabilities": [
                {
                    "id": "rainfall",
                    "name": "Rainfall",
                    "description": "Current rainfall observations.",
                    "provider": "weather",
                }
            ],
            "next_cursor": "1",
        },
        metadata=ToolExecutionMetadata(duration_ms=3),
    )

    message = AgentLoop._tool_result_messages(  # pyright: ignore[reportPrivateUsage]
        [LLMToolCall(id="call-1", name=result.tool_name, arguments={})],
        [result],
    )[0]
    observation = json.loads(message["content"])

    assert observation["status"] == "success"
    assert observation["result"]["capabilities"][0]["id"] == "rainfall"
    assert observation["pagination"]["next_cursor"] == "1"

###############################################################################
def test_capability_description_observation_preserves_contract_and_schema() -> None:
    result = ToolResult(
        call_id="call-1",
        tool_name="describe_geospatial_capability",
        status="success",
        summary="Described rainfall.",
        data={
            "capability_id": "rainfall",
            "manifest": {
                "id": "rainfall",
                "name": "Rainfall",
                "provider": "weather",
                "description": "Rainfall observations.",
            },
            "argument_schema": {
                "type": "object",
                "required": ["location"],
                "properties": {"location": {"type": "string"}},
            },
            "execution_contract": {
                "supported_operations": ["show", "forecast"],
                "required_inputs": ["location"],
            },
        },
        metadata=ToolExecutionMetadata(duration_ms=3),
    )

    message = AgentLoop._tool_result_messages(  # pyright: ignore[reportPrivateUsage]
        [LLMToolCall(id="call-1", name=result.tool_name, arguments={})],
        [result],
    )[0]
    observation = json.loads(message["content"])

    assert observation["result"]["capability_id"] == "rainfall"
    assert observation["result"]["argument_schema"]["required"] == ["location"]
    assert observation["result"]["execution_contract"]["supported_operations"] == [
        "show",
        "forecast",
    ]

###############################################################################
def test_working_state_remains_valid_json_when_compacted() -> None:
    state = _state()
    state.route = CapabilityRoute(
        primary_domain=CapabilityDomain.DATA_RETRIEVAL,
        task_mode="execute",
        presentation="text",
        requires_location=False,
    )
    state.tool_results = [
        ToolResult(
            call_id="call-1",
            tool_name="test_tool",
            status="success",
            summary="x" * 10_000,
            metadata=ToolExecutionMetadata(duration_ms=0),
        )
    ]

    working = AgentLoop._working_state_message(  # pyright: ignore[reportPrivateUsage]
        state, 256
    )

    payload = json.loads(working)
    assert payload["phase"] == state.phase.value
    assert payload["goal"] is None
    assert payload["completion_contract"] is None

###############################################################################
def test_compacted_working_state_retains_goal_and_completion_invariants() -> None:
    state = _state()
    state.route = CapabilityRoute(
        primary_domain=CapabilityDomain.DATA_RETRIEVAL,
        task_mode="execute",
        presentation="text",
        requires_location=True,
        capability_queries=["rainfall"],
    )
    state.goal = AgentGoal(
        goal="Find rainfall around Lugano",
        task_mode="execute",
        presentation="text",
        operation="show",
        requires_location=True,
        target_ids=["lugano"],
    )
    state.completion_contract = CompletionContract(
        operation="show",
        requirements=["location_resolved", "required_data_retrieved"],
        location_required=True,
        evidence_required=True,
    )

    payload = json.loads(
        AgentLoop._working_state_message(  # pyright: ignore[reportPrivateUsage]
            state, 256
        )
    )

    assert payload["goal"]["operation"] == "show"
    assert payload["completion_contract"]["requirements"] == [
        "location_resolved",
        "required_data_retrieved",
    ]
    assert payload["route"]["primary_domain"] == "data_retrieval"

###############################################################################
def test_responses_protocol_items_are_retained_for_the_next_model_turn() -> None:
    result = LLMResult(
        content="",
        raw={
            "output": [
                {"type": "reasoning", "id": "reasoning-1"},
                {
                    "type": "function_call",
                    "call_id": "call-1",
                    "name": "test_tool",
                    "arguments": "{}",
                },
            ]
        },
        tool_calls=[LLMToolCall(id="call-1", name="test_tool", arguments={})],
    )

    messages = AgentLoop._assistant_and_tool_messages(  # pyright: ignore[reportPrivateUsage]
        result
    )

    assert [item["type"] for item in messages] == ["reasoning", "function_call"]

###############################################################################
@pytest.mark.asyncio
async def test_successful_duplicate_call_replays_without_external_tool_execution() -> None:
    provider = FakeProvider(
        [
            _route_call(),
            LLMResult(
                content="",
                tool_calls=[
                    LLMToolCall(id="call-1", name="test_tool", arguments={})
                ],
            ),
            LLMResult(
                content="",
                tool_calls=[
                    LLMToolCall(id="call-2", name="test_tool", arguments={})
                ],
            ),
            LLMResult(content="Duplicate handled."),
        ]
    )
    outcome = await _loop(provider).run(
        AgentLoopRequest(
            provider="fake",
            model="fake-model",
            state=_state(),
            budget=AgentExecutionBudget(total_seconds=10, hard_max_seconds=10),
        )
    )

    assert outcome.final_text == "Duplicate handled."
    assert outcome.state.tool_calls == 1
    assert len(outcome.tool_results) == 2

###############################################################################
class RetryThenUnexpectedProvider:

    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        self.calls = 0

    # -------------------------------------------------------------------------
    async def achat(self, request: Any, **kwargs: Any) -> LLMResult:
        self.calls += 1
        if self.calls == 1:
            raise LLMProviderRequestError(
                provider="fake",
                model="fake-model",
                stage="chat",
                code="temporary_failure",
                retryable=True,
            )
        raise AssertionError("The model retry exceeded the run deadline.")

###############################################################################
@pytest.mark.asyncio
async def test_model_retry_cannot_restart_after_run_deadline() -> None:
    provider = RetryThenUnexpectedProvider()
    loop = _loop(provider)  # type: ignore[arg-type]
    request = AgentLoopRequest(
        provider="fake",
        model="fake-model",
        state=_state(),
        budget=AgentExecutionBudget(total_seconds=0.03, hard_max_seconds=0.03),
    )

    with pytest.raises(TimeoutError):
        await loop._model_call(  # pyright: ignore[reportPrivateUsage]
            request,
            provider,  # type: ignore[arg-type]
            [],
            [],
            tool_choice="none",
        )

    assert provider.calls == 1

###############################################################################
@pytest.mark.asyncio
async def test_map_route_text_cannot_stop_before_a_map_candidate_exists() -> None:
    provider = FakeProvider(
        [
            LLMResult(
                content="",
                tool_calls=[
                    LLMToolCall(
                        id="route-map",
                        name="route_request",
                        arguments={
                            "primary_domain": "map_rendering",
                            "task_mode": "execute",
                            "presentation": "map",
                            "requires_location": False,
                            "capability_queries": ["basemap"],
                        },
                    )
                ],
            ),
            LLMResult(content="I prepared the map."),
        ]
    )
    outcome = await _loop(provider).run(
        AgentLoopRequest(
            provider="fake",
            model="fake-model",
            state=_state(),
            budget=AgentExecutionBudget(total_seconds=10, hard_max_seconds=10),
        )
    )

    assert outcome.stopped_reason == "failed"
    assert outcome.failure_category == "model_capability"
