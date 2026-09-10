from __future__ import annotations

from collections import deque
from typing import Any

import pytest
from pydantic import BaseModel

from server.domain.agent.capability_domains import CapabilityDomain
from server.domain.agent.capability_route import AgentPhase, AgentState
from server.domain.agent.reliability import AgentExecutionBudget
from server.domain.agent.tool_result import ToolExecutionMetadata, ToolResult
from server.domain.agent.tools import RegisteredTool
from server.domain.llm.types import LLMResult, LLMToolCall, LLMToolDefinition
from server.services.agent.agent_loop import AgentLoop, AgentLoopRequest
from server.services.agent.capability_router import CapabilityRouter
from server.services.agent.tool_executor import ToolExecutor
from server.services.agent.tool_registry import ToolRegistry


class FakeProvider:
    def __init__(self, results: list[LLMResult]) -> None:
        self.results = deque(results)
        self.requests: list[dict[str, Any]] = []

    async def achat(self, request: Any, **kwargs: Any) -> LLMResult:
        self.requests.append({"request": request, "kwargs": kwargs})
        return self.results.popleft()


class FakeFactory:
    def __init__(self, provider: FakeProvider) -> None:
        self.provider = provider

    def get_provider(self, provider: str) -> FakeProvider:
        return self.provider


class FakeCapabilityRegistry:
    def get_capability(self, capability_id: str) -> dict[str, object] | None:
        if capability_id == "places:hospitals":
            return {"id": capability_id, "provider": "overpass"}
        return None

    def shortlist(self, **kwargs: Any) -> list[dict[str, object]]:
        return [{"id": "places:hospitals"}]


class FakeRuntimeRegistry:
    def is_enabled(self, capability_id: str) -> bool:
        return True

    def access_available(self, capability_id: str) -> bool:
        return True


class EmptyInput(BaseModel):
    pass


async def _answer_handler(arguments: BaseModel, state: AgentState) -> ToolResult:
    return ToolResult(
        call_id="handler-call",
        tool_name="test_tool",
        status="success",
        summary="tool completed",
        metadata=ToolExecutionMetadata(duration_ms=0),
    )


def _loop(provider: FakeProvider) -> AgentLoop:
    capability_registry = FakeCapabilityRegistry()
    registry = ToolRegistry(runtime_registry=FakeRuntimeRegistry())  # type: ignore[arg-type]
    registry.register(
        RegisteredTool(
            definition=LLMToolDefinition(
                name="test_tool",
                description="test",
                parameters_json_schema={"type": "object"},
            ),
            input_model=EmptyInput,
            handler=_answer_handler,
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
    return AgentLoop(
        provider_factory=FakeFactory(provider),  # type: ignore[arg-type]
        capability_router=CapabilityRouter(
            capability_registry=capability_registry,  # type: ignore[arg-type]
            runtime_registry=FakeRuntimeRegistry(),  # type: ignore[arg-type]
        ),
        tool_registry=registry,
        tool_executor=ToolExecutor(tool_registry=registry),
    )


def _state() -> AgentState:
    return AgentState(
        request_id="request-1",
        conversation_id="conversation-1",
        phase=AgentPhase.RECEIVE_REQUEST,
        user_message="find hospitals",
    )


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
    assert state.route is not None
    assert state.capability_ids == ["places:hospitals"]
    assert [item["kwargs"]["tool_choice"] for item in provider.requests] == [
        "required",
        "auto",
    ]
    assert state.transition_trace


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
