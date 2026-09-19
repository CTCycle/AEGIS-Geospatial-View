from __future__ import annotations

import asyncio
import json
from collections import deque
from typing import Any

import pytest
from pydantic import BaseModel

from server.domain.agent.capability_domains import CapabilityDomain
from server.domain.agent.capability_route import AgentPhase, AgentRunState
from server.domain.agent.reliability import AgentExecutionBudget
from server.domain.agent.tool_result import (
    ToolExecutionError,
    ToolExecutionMetadata,
    ToolResult,
)
from server.domain.agent.tools import RegisteredTool
from server.domain.llm.types import LLMResult, LLMToolCall, LLMToolDefinition
from server.services.agent.agent_loop import AgentLoop, AgentLoopRequest
from server.services.agent.capability_router import CapabilityRouter
from server.services.agent.tool_definitions import (
    CapabilityDiscoveryInput,
    ExecuteCapabilityInput,
    RouteRequestInput,
)
from server.services.agent.tool_executor import ToolExecutor
from server.services.agent.tool_handlers.catalog import CatalogToolHandler
from server.services.agent.policy_engine import PolicyEngine
from server.services.agent.tool_registry import ToolRegistry


###############################################################################
class _Provider:

    # -------------------------------------------------------------------------
    def __init__(self, results: list[LLMResult]) -> None:
        self.results = deque(results)
        self.requests: list[Any] = []

    # -------------------------------------------------------------------------
    async def achat(self, request: Any, **_kwargs: Any) -> LLMResult:
        self.requests.append(request)
        return self.results.popleft()


###############################################################################
class _BlockingProvider:

    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        self.entered = asyncio.Event()
        self.cancelled = False

    # -------------------------------------------------------------------------
    async def achat(self, _request: Any, **_kwargs: Any) -> LLMResult:
        self.entered.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        raise AssertionError("The cancelled provider call unexpectedly returned.")


###############################################################################
class _Factory:

    # -------------------------------------------------------------------------
    def __init__(self, provider: _Provider) -> None:
        self.provider = provider

    # -------------------------------------------------------------------------
    def get_provider(self, _provider: str) -> _Provider:
        return self.provider


###############################################################################
class _Runtime:

    # -------------------------------------------------------------------------
    def is_enabled(self, _capability_id: str) -> bool:
        return True

    # -------------------------------------------------------------------------
    def access_available(self, _capability_id: str) -> bool:
        return True


###############################################################################
class _Catalog:

    # -------------------------------------------------------------------------
    def __init__(self, *, empty_first: bool) -> None:
        self.empty_first = empty_first
        self.shortlist_calls = 0
        self.capabilities = {
            "primary-source": {
                "id": "primary-source",
                "name": "Primary source",
                "description": "Primary geospatial source.",
                "provider": "primary",
                "capabilityKind": "vector-overlay",
            },
            "alternate-source": {
                "id": "alternate-source",
                "name": "Alternate source",
                "description": "Equivalent alternate geospatial source.",
                "provider": "alternate",
                "capabilityKind": "vector-overlay",
            },
        }

    # -------------------------------------------------------------------------
    def get_capability(self, capability_id: str) -> dict[str, object] | None:
        return self.capabilities.get(capability_id)

    # -------------------------------------------------------------------------
    def shortlist(self, **_kwargs: Any) -> list[dict[str, object]]:
        self.shortlist_calls += 1
        if self.empty_first and self.shortlist_calls == 1:
            return []
        return list(self.capabilities.values())

    # -------------------------------------------------------------------------
    def execution_contract(self, _capability_id: str) -> dict[str, object]:
        return {
            "supported_operations": ["show"],
            "supported_scope_kinds": ["point", "bbox"],
        }


###############################################################################
def _route_call(*, complex_route: bool = False) -> LLMResult:
    arguments: dict[str, Any] = {
        "primary_domain": "data_retrieval",
        "task_mode": "execute",
        "presentation": "text",
        "requires_location": False,
        "capability_queries": ["obscure geospatial data"],
    }
    if complex_route:
        arguments["secondary_domains"] = ["spatial_analysis"]
    return LLMResult(
        content="",
        tool_calls=[
            LLMToolCall(
                id="route-1",
                name="route_request",
                arguments=arguments,
            )
        ],
    )


###############################################################################
def _state() -> AgentRunState:
    return AgentRunState(
        request_id="request-1",
        conversation_id="conversation-1",
        phase=AgentPhase.RECEIVE_REQUEST,
        user_message="Find obscure geospatial data.",
    )


###############################################################################
def _registration(
    *,
    name: str,
    input_model: type[BaseModel],
    handler: Any,
    prerequisites: frozenset[str],
    phase: AgentPhase = AgentPhase.BUILD_TOOL_CONTEXT,
    visibility: str = "model",
) -> RegisteredTool:
    return RegisteredTool(
        definition=LLMToolDefinition(
            name=name,
            description=f"Test {name}.",
            parameters_json_schema=input_model.model_json_schema(),
        ),
        input_model=input_model,
        handler=handler,
        domains=frozenset({CapabilityDomain.MIXED}),
        phases=frozenset({phase}),
        visibility=visibility,  # type: ignore[arg-type]
        prerequisites=prerequisites,
        timeout_key="tool_execution_seconds",
        idempotent=name.startswith("discover_"),
        result_normalizer=lambda value, call_id: value.model_copy(
            update={"call_id": call_id}
        ),
    )


###############################################################################
def _loop(
    provider: _Provider,
    *,
    catalog: _Catalog,
    execute_handler: Any,
) -> AgentLoop:
    runtime = _Runtime()
    registry = ToolRegistry(runtime_registry=runtime)  # type: ignore[arg-type]
    catalog_handler = CatalogToolHandler(
        capability_registry=catalog,  # type: ignore[arg-type]
        runtime_registry=runtime,  # type: ignore[arg-type]
    )
    registry.register(
        _registration(
            name="route_request",
            input_model=RouteRequestInput,
            handler=execute_handler,
            prerequisites=frozenset(),
            phase=AgentPhase.ROUTE_REQUEST,
            visibility="internal",
        )
    )
    registry.register(
        _registration(
            name="discover_geospatial_capabilities",
            input_model=CapabilityDiscoveryInput,
            handler=catalog_handler.discover,
            prerequisites=frozenset({"route", "capability_shortlist_missing"}),
        )
    )
    registry.register(
        _registration(
            name="execute_geospatial_capability",
            input_model=ExecuteCapabilityInput,
            handler=execute_handler,
            prerequisites=frozenset({"route", "capability_shortlist"}),
        )
    )
    return AgentLoop(
        provider_factory=_Factory(provider),  # type: ignore[arg-type]
        capability_router=CapabilityRouter(
            capability_registry=catalog,  # type: ignore[arg-type]
            runtime_registry=runtime,  # type: ignore[arg-type]
        ),
        tool_registry=registry,
        tool_executor=ToolExecutor(
            tool_registry=registry,
            policy_engine=PolicyEngine(
                capability_registry=catalog,  # type: ignore[arg-type]
                runtime_registry=runtime,  # type: ignore[arg-type]
            ),
        ),
    )


###############################################################################
def _success(call_id: str, capability_id: str) -> ToolResult:
    return ToolResult(
        call_id=call_id,
        tool_name="execute_geospatial_capability",
        status="success",
        summary=f"Retrieved data from {capability_id}.",
        data={"features": [{"id": "feature-1"}]},
        evidence_refs=[f"evidence:{capability_id}"],
        metadata=ToolExecutionMetadata(
            capability_id=capability_id,
            provider_id=capability_id,
            duration_ms=0,
            result_type="features",
            result_status="success",
        ),
    )


###############################################################################
@pytest.mark.asyncio
async def test_empty_shortlist_exposes_discovery_and_observes_descriptors() -> None:
    async def execute(_arguments: ExecuteCapabilityInput, _state: AgentRunState) -> ToolResult:
        return _success("handler-call", "primary-source")

    provider = _Provider(
        [
            _route_call(),
            LLMResult(
                content="",
                tool_calls=[
                    LLMToolCall(
                        id="discover-1",
                        name="discover_geospatial_capabilities",
                        arguments={"query": "obscure geospatial data"},
                    )
                ],
            ),
            LLMResult(
                content="",
                tool_calls=[
                    LLMToolCall(
                        id="execute-1",
                        name="execute_geospatial_capability",
                        arguments={"capability_id": "primary-source"},
                    )
                ],
            ),
            LLMResult(content="The discovered source answered the request."),
        ]
    )
    outcome = await _loop(
        provider,
        catalog=_Catalog(empty_first=True),
        execute_handler=execute,
    ).run(
        AgentLoopRequest(
            provider="fake",
            model="fake-model",
            state=_state(),
            budget=AgentExecutionBudget(total_seconds=10, hard_max_seconds=10),
            max_model_calls=6,
            max_tool_calls=6,
            max_state_transitions=32,
        )
    )

    assert outcome.stopped_reason == "goal_satisfied"
    assert outcome.state.capability_ids == ["primary-source", "alternate-source"]
    assert any(
        "primary-source" in json.dumps(request.messages)
        for request in provider.requests[1:]
    )


###############################################################################
@pytest.mark.asyncio
async def test_replan_reopens_discovery_and_selects_an_alternate_source() -> None:
    calls: list[str] = []

    async def execute(
        arguments: ExecuteCapabilityInput, _state: AgentRunState
    ) -> ToolResult:
        calls.append(arguments.capability_id)
        if arguments.capability_id == "primary-source":
            return ToolResult(
                call_id="handler-call",
                tool_name="execute_geospatial_capability",
                status="failed",
                summary="The primary provider timed out.",
                error=ToolExecutionError(
                    error_type="provider_unavailable",
                    code="provider_timeout",
                    message="The primary provider timed out.",
                    retryable=False,
                    recovery="replan",
                ),
                metadata=ToolExecutionMetadata(
                    capability_id="primary-source",
                    provider_id="primary",
                    duration_ms=0,
                ),
            )
        return _success("handler-call", arguments.capability_id)

    provider = _Provider(
        [
            _route_call(complex_route=True),
            LLMResult(
                content="",
                tool_calls=[
                    LLMToolCall(
                        id="execute-primary",
                        name="execute_geospatial_capability",
                        arguments={"capability_id": "primary-source"},
                    )
                ],
            ),
            LLMResult(
                content="",
                tool_calls=[
                    LLMToolCall(
                        id="discover-alternate",
                        name="discover_geospatial_capabilities",
                        arguments={},
                    )
                ],
            ),
            LLMResult(
                content="",
                tool_calls=[
                    LLMToolCall(
                        id="execute-alternate",
                        name="execute_geospatial_capability",
                        arguments={"capability_id": "alternate-source"},
                    )
                ],
            ),
            LLMResult(content="The alternate source answered the request."),
        ]
    )
    outcome = await _loop(
        provider,
        catalog=_Catalog(empty_first=False),
        execute_handler=execute,
    ).run(
        AgentLoopRequest(
            provider="fake",
            model="fake-model",
            state=_state(),
            budget=AgentExecutionBudget(total_seconds=10, hard_max_seconds=10),
            max_model_calls=8,
            max_tool_calls=8,
            max_state_transitions=48,
        )
    )

    assert outcome.stopped_reason == "goal_satisfied"
    assert calls == ["primary-source", "alternate-source"]
    assert outcome.state.excluded_capability_ids == ["primary-source"]
    assert outcome.state.capability_ids == ["alternate-source"]
    assert any(
        "provider_timeout" in json.dumps(request.messages)
        for request in provider.requests
    )


###############################################################################
@pytest.mark.asyncio
async def test_valid_empty_result_allows_a_materially_different_alternate_query() -> None:
    calls: list[str] = []

    async def execute(
        arguments: ExecuteCapabilityInput, _state: AgentRunState
    ) -> ToolResult:
        calls.append(arguments.capability_id)
        if arguments.capability_id == "primary-source":
            return ToolResult(
                call_id="handler-call",
                tool_name="execute_geospatial_capability",
                status="valid_empty",
                semantic_outcome="not_found",
                summary="The primary source returned no matching features.",
                data={"features": []},
                metadata=ToolExecutionMetadata(
                    capability_id="primary-source",
                    provider_id="primary",
                    duration_ms=0,
                    result_type="features",
                    result_status="valid_empty",
                ),
            )
        return _success("handler-call", arguments.capability_id)

    provider = _Provider(
        [
            _route_call(complex_route=True),
            LLMResult(
                content="",
                tool_calls=[
                    LLMToolCall(
                        id="execute-empty",
                        name="execute_geospatial_capability",
                        arguments={"capability_id": "primary-source"},
                    )
                ],
            ),
            LLMResult(
                content="",
                tool_calls=[
                    LLMToolCall(
                        id="discover-alternate",
                        name="discover_geospatial_capabilities",
                        arguments={"query": "widened hospitals"},
                    )
                ],
            ),
            LLMResult(
                content="",
                tool_calls=[
                    LLMToolCall(
                        id="execute-alternate",
                        name="execute_geospatial_capability",
                        arguments={
                            "capability_id": "alternate-source",
                            "filters": {"widened": True},
                        },
                    )
                ],
            ),
            LLMResult(content="The alternate query found the requested data."),
        ]
    )
    outcome = await _loop(
        provider,
        catalog=_Catalog(empty_first=False),
        execute_handler=execute,
    ).run(
        AgentLoopRequest(
            provider="fake",
            model="fake-model",
            state=_state(),
            budget=AgentExecutionBudget(total_seconds=10, hard_max_seconds=10),
            max_model_calls=8,
            max_tool_calls=8,
            max_state_transitions=48,
        )
    )

    assert outcome.stopped_reason == "goal_satisfied"
    assert calls == ["primary-source", "alternate-source"]
    assert [result.status for result in outcome.tool_results] == [
        "valid_empty",
        "success",
        "success",
    ]


###############################################################################
@pytest.mark.asyncio
async def test_malformed_tool_call_is_corrected_in_the_same_native_run() -> None:
    calls: list[str] = []

    async def execute(
        arguments: ExecuteCapabilityInput, _state: AgentRunState
    ) -> ToolResult:
        calls.append(arguments.capability_id)
        return _success("handler-call", arguments.capability_id)

    provider = _Provider(
        [
            _route_call(),
            LLMResult(
                content="",
                tool_calls=[
                    LLMToolCall(
                        id="malformed-call",
                        name="execute_geospatial_capability",
                        arguments=None,
                        parse_error="invalid_json",
                    )
                ],
            ),
            LLMResult(
                content="",
                tool_calls=[
                    LLMToolCall(
                        id="corrected-call",
                        name="execute_geospatial_capability",
                        arguments={"capability_id": "primary-source"},
                    )
                ],
            ),
            LLMResult(content="The corrected call completed the request."),
        ]
    )
    outcome = await _loop(
        provider,
        catalog=_Catalog(empty_first=False),
        execute_handler=execute,
    ).run(
        AgentLoopRequest(
            provider="fake",
            model="fake-model",
            state=_state(),
            budget=AgentExecutionBudget(total_seconds=10, hard_max_seconds=10),
            max_model_calls=8,
            max_tool_calls=8,
            max_state_transitions=48,
        )
    )

    assert outcome.stopped_reason == "goal_satisfied"
    assert calls == ["primary-source"]
    assert outcome.state.validation_corrections == 1
    assert [result.status for result in outcome.tool_results] == [
        "failed",
        "success",
    ]


###############################################################################
@pytest.mark.asyncio
async def test_successful_native_data_stops_before_redundant_model_turns() -> None:
    calls: list[int] = []

    async def execute(
        arguments: ExecuteCapabilityInput, _state: AgentRunState
    ) -> ToolResult:
        calls.append(int(arguments.filters["step"]))
        return _success("handler-call", "primary-source")

    model_results = [_route_call(complex_route=True)]
    model_results.extend(
        LLMResult(
            content="",
            tool_calls=[
                LLMToolCall(
                    id=f"execute-{step}",
                    name="execute_geospatial_capability",
                    arguments={
                        "capability_id": "primary-source",
                        "filters": {"step": step},
                    },
                )
            ],
        )
        for step in range(8)
    )
    model_results.append(LLMResult(content="The bounded native trajectory completed."))
    provider = _Provider(model_results)
    state = _state()
    state.context_hydrated = True
    outcome = await _loop(
        provider,
        catalog=_Catalog(empty_first=False),
        execute_handler=execute,
    ).run(
        AgentLoopRequest(
            provider="fake",
            model="fake-model",
            state=state,
            budget=AgentExecutionBudget(total_seconds=10, hard_max_seconds=10),
            max_iterations=12,
            max_model_calls=10,
            max_tool_calls=12,
            max_state_transitions=128,
        )
    )

    assert outcome.stopped_reason == "goal_satisfied"
    # A successful provider result satisfies the data obligation.  The loop
    # must reserve one finalizer turn and stop instead of replaying the model's
    # redundant follow-up calls until the action budget is exhausted.
    assert outcome.model_calls == 3
    assert outcome.state.tool_calls == 1
    assert calls == [0]
    assert len(provider.requests) == 3
    assert any(
        "CANONICAL_NATIVE_CONTEXT" in str(message.get("content", ""))
        for message in provider.requests[-1].messages
    )


###############################################################################
@pytest.mark.asyncio
async def test_cancellation_during_model_call_returns_a_cancelled_outcome() -> None:
    provider = _BlockingProvider()

    async def execute(_arguments: ExecuteCapabilityInput, _state: AgentRunState) -> ToolResult:
        return _success("handler-call", "primary-source")

    task = asyncio.create_task(
        _loop(
            provider,  # type: ignore[arg-type]
            catalog=_Catalog(empty_first=False),
            execute_handler=execute,
        ).run(
            AgentLoopRequest(
                provider="fake",
                model="fake-model",
                state=_state(),
                budget=AgentExecutionBudget(total_seconds=10, hard_max_seconds=10),
            )
        )
    )
    await asyncio.wait_for(provider.entered.wait(), timeout=1)
    task.cancel()
    outcome = await task

    assert provider.cancelled is True
    assert outcome.stopped_reason == "cancelled"
    assert outcome.state.termination_reason == "cancelled"
    assert outcome.state.tool_calls == 0


###############################################################################
@pytest.mark.asyncio
async def test_cancellation_during_tool_call_does_not_apply_a_partial_result() -> None:
    provider = _Provider(
        [
            _route_call(),
            LLMResult(
                content="",
                tool_calls=[
                    LLMToolCall(
                        id="blocked-tool",
                        name="execute_geospatial_capability",
                        arguments={"capability_id": "primary-source"},
                    )
                ],
            ),
        ]
    )
    entered = asyncio.Event()

    async def execute(
        _arguments: ExecuteCapabilityInput, _state: AgentRunState
    ) -> ToolResult:
        entered.set()
        await asyncio.Event().wait()
        return _success("handler-call", "primary-source")

    task = asyncio.create_task(
        _loop(
            provider,
            catalog=_Catalog(empty_first=False),
            execute_handler=execute,
        ).run(
            AgentLoopRequest(
                provider="fake",
                model="fake-model",
                state=_state(),
                budget=AgentExecutionBudget(total_seconds=10, hard_max_seconds=10),
            )
        )
    )
    await asyncio.wait_for(entered.wait(), timeout=1)
    task.cancel()
    outcome = await task

    assert outcome.stopped_reason == "cancelled"
    assert outcome.state.termination_reason == "cancelled"
    assert outcome.state.tool_calls == 1
    assert outcome.state.tool_results == []
