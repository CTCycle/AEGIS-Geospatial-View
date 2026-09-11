from __future__ import annotations

from collections import deque
from typing import Any

from pydantic import BaseModel

from server.domain.agent.capability_domains import CapabilityDomain
from server.domain.agent.capability_route import AgentPhase
from server.domain.agent.decision import ResolvedLocation
from server.domain.agent.reliability import AgentExecutionBudget
from server.domain.agent.tool_result import ToolExecutionMetadata, ToolResult
from server.domain.agent.tools import RegisteredTool
from server.domain.llm.types import LLMResult, LLMToolCall, LLMToolDefinition
from server.services.agent.agent_loop import AgentLoop
from server.services.agent.capability_router import CapabilityRouter
from server.services.agent.native_v2_turn import (
    NativeV2TurnRequest,
    NativeV2TurnRunner,
)
from server.services.agent.tool_executor import ToolExecutor
from server.services.agent.tool_registry import ToolRegistry


class _Provider:
    def __init__(self, results: list[LLMResult]) -> None:
        self.results = deque(results)

    async def achat(self, _request: Any, **_kwargs: Any) -> LLMResult:
        return self.results.popleft()


class _Factory:
    def __init__(self, provider: _Provider) -> None:
        self.provider = provider

    def get_provider(self, _provider: str) -> _Provider:
        return self.provider


class _CapabilityRegistry:
    def get_capability(self, capability_id: str) -> dict[str, Any] | None:
        return {"id": capability_id} if capability_id == "places:hospitals" else None

    def shortlist(self, **_kwargs: Any) -> list[dict[str, Any]]:
        return [{"id": "places:hospitals"}]


class _RuntimeRegistry:
    def is_enabled(self, _capability_id: str) -> bool:
        return True

    def access_available(self, _capability_id: str) -> bool:
        return True


class _Input(BaseModel):
    pass


async def _handler(_arguments: BaseModel, _state: Any) -> ToolResult:
    return ToolResult(
        call_id="handler",
        tool_name="test_tool",
        status="success",
        summary="ok",
        metadata=ToolExecutionMetadata(duration_ms=0),
    )


def _runner(provider: _Provider) -> NativeV2TurnRunner:
    runtime = _RuntimeRegistry()
    registry = ToolRegistry(runtime_registry=runtime)  # type: ignore[arg-type]
    registry.register(
        RegisteredTool(
            definition=LLMToolDefinition(
                name="test_tool",
                description="Test tool",
                parameters_json_schema={"type": "object"},
            ),
            input_model=_Input,
            handler=_handler,
            domains=frozenset({CapabilityDomain.DATA_RETRIEVAL}),
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
    loop = AgentLoop(
        provider_factory=_Factory(provider),  # type: ignore[arg-type]
        capability_router=CapabilityRouter(
            capability_registry=_CapabilityRegistry(),  # type: ignore[arg-type]
            runtime_registry=runtime,  # type: ignore[arg-type]
        ),
        tool_registry=registry,
        tool_executor=ToolExecutor(tool_registry=registry),
    )
    return NativeV2TurnRunner(agent_loop=loop)


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


async def _run(provider: _Provider):
    return await _runner(provider).run(
        NativeV2TurnRequest(
            request_id="request-1",
            conversation_id="conversation-1",
            user_message="find hospitals",
            provider="fake",
            model="fake-model",
            budget=AgentExecutionBudget(total_seconds=10, hard_max_seconds=10),
        )
    )


async def test_native_runner_returns_bounded_response_contract() -> None:
    response = await _run(_Provider([_route_call(), LLMResult(content="Found them.")]))

    assert response.assistant_message == "Found them."
    assert response.route is not None
    assert response.operation.kind == "direct_answer"
    assert response.presentation_status == "not_requested"
    assert response.execution_trace is not None
    assert response.execution_trace["transition_trace"]


async def test_native_runner_marks_map_text_without_candidate_failed() -> None:
    route = _route_call()
    route.tool_calls[0] = LLMToolCall(
        id="route-map",
        name="route_request",
        arguments={
            "primary_domain": "map_rendering",
            "task_mode": "execute",
            "presentation": "map",
            "requires_location": False,
        },
    )
    response = await _run(_Provider([route, LLMResult(content="Map ready.")]))

    assert response.operation.status == "failed"
    assert response.presentation_status == "failed"


async def test_native_runner_preserves_location_refs_in_response() -> None:
    location = ResolvedLocation(
        label="Rome",
        latitude=41.9028,
        longitude=12.4964,
        country="Italy",
        city="Rome",
        location_type="city",
        source="test",
        confidence=1.0,
    )
    response = await _runner(
        _Provider([_route_call(), LLMResult(content="Found Rome.")])
    ).run(
        NativeV2TurnRequest(
            request_id="request-location",
            conversation_id="conversation-location",
            user_message="find hospitals in Rome",
            provider="fake",
            model="fake-model",
            budget=AgentExecutionBudget(total_seconds=10, hard_max_seconds=10),
            location_refs={"rome": location},
        )
    )

    assert response.location_refs["rome"] == location
