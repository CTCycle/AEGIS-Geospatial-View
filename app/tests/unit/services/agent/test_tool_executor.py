from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest
from pydantic import BaseModel, ConfigDict

from server.domain.agent.capability_domains import CapabilityDomain
from server.domain.agent.capability_route import AgentPhase, AgentState
from server.domain.agent.reliability import AgentExecutionBudget
from server.domain.agent.tool_result import ToolExecutionMetadata, ToolResult
from server.domain.agent.tools import RegisteredTool
from server.domain.llm.types import LLMToolCall, LLMToolDefinition
from server.services.agent.tool_executor import ToolExecutor
from server.services.agent.tool_registry import ToolRegistry


class _Input(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: int


class _Policy:
    def __init__(self, allowed: bool = True) -> None:
        self.allowed = allowed

    def authorize(self, _tool: RegisteredTool, _arguments: BaseModel, _state: AgentState):
        return cast(Any, type("Authorization", (), {"allowed": self.allowed, "reason": "blocked"})())


def _state() -> AgentState:
    return AgentState(
        request_id="request-1",
        conversation_id="conversation-1",
        phase=AgentPhase.MODEL_STEP,
        user_message="Use the tool.",
    )


def _budget() -> AgentExecutionBudget:
    return AgentExecutionBudget(total_seconds=5.0)


def _tool(
    handler: Any,
    *,
    semantic_validator: Any | None = None,
) -> RegisteredTool:
    def normalize(value: Any, call_id: str) -> ToolResult:
        return ToolResult(
            call_id=call_id,
            tool_name="test_tool",
            status="success",
            summary=str(value),
            metadata=ToolExecutionMetadata(duration_ms=0),
        )

    return RegisteredTool(
        definition=LLMToolDefinition(
            name="test_tool",
            description="Test tool",
            parameters_json_schema=_Input.model_json_schema(),
        ),
        input_model=_Input,
        handler=handler,
        domains=frozenset({CapabilityDomain.DATA_RETRIEVAL}),
        phases=frozenset({AgentPhase.MODEL_STEP}),
        visibility="model",
        prerequisites=frozenset(),
        timeout_key="tool_execution_seconds",
        idempotent=True,
        result_normalizer=normalize,
        semantic_validator=semantic_validator,
    )


def test_executor_validates_once_and_normalizes_success() -> None:
    calls: list[int] = []

    async def handler(arguments: _Input, _state: AgentState) -> dict[str, Any]:
        calls.append(arguments.value)
        return {"value": arguments.value}

    registry = ToolRegistry(runtime_registry=cast(Any, None))
    registry.register(_tool(handler))
    result = asyncio.run(
        ToolExecutor(tool_registry=registry).execute_tool(
            LLMToolCall(id="call-1", name="test_tool", arguments={"value": 3}),
            _state(),
            _budget(),
        )
    )

    assert result.status == "success"
    assert calls == [3]


def test_malformed_call_never_reaches_the_handler() -> None:
    calls: list[int] = []

    async def handler(_arguments: _Input, _state: AgentState) -> dict[str, Any]:
        calls.append(1)
        return {}

    registry = ToolRegistry(runtime_registry=cast(Any, None))
    registry.register(_tool(handler))
    result = asyncio.run(
        ToolExecutor(tool_registry=registry).execute_tool(
            LLMToolCall(
                id="call-1",
                name="test_tool",
                arguments=None,
                parse_error="invalid_json",
            ),
            _state(),
            _budget(),
        )
    )

    assert result.error is not None
    assert result.error.error_type == "malformed_call"
    assert calls == []


def test_schema_semantic_policy_and_timeout_failures_are_typed() -> None:
    async def handler(_arguments: _Input, _state: AgentState) -> dict[str, Any]:
        await asyncio.sleep(0.05)
        return {}

    def reject(_arguments: BaseModel, _state: AgentState) -> list[str]:
        return ["value is not allowed"]

    registry = ToolRegistry(runtime_registry=cast(Any, None))
    registry.register(_tool(handler, semantic_validator=reject))
    executor = ToolExecutor(tool_registry=registry, policy_engine=_Policy(False))

    schema_result = asyncio.run(
        executor.execute_tool(
            LLMToolCall(id="schema", name="test_tool", arguments={"unexpected": 1}),
            _state(),
            _budget(),
        )
    )
    policy_registry = ToolRegistry(runtime_registry=cast(Any, None))
    policy_registry.register(_tool(handler))
    policy_result = asyncio.run(
        ToolExecutor(tool_registry=policy_registry, policy_engine=_Policy(False)).execute_tool(
            LLMToolCall(id="policy", name="test_tool", arguments={"value": 1}),
            _state(),
            _budget(),
        )
    )

    assert schema_result.error is not None
    assert schema_result.error.error_type == "schema_validation"
    assert policy_result.error is not None
    assert policy_result.error.error_type == "policy_rejection"

    timeout_registry = ToolRegistry(runtime_registry=cast(Any, None))
    timeout_registry.register(_tool(handler))
    timeout_result = asyncio.run(
        ToolExecutor(tool_registry=timeout_registry, timeout_seconds=0.01).execute_tool(
            LLMToolCall(id="timeout", name="test_tool", arguments={"value": 1}),
            _state(),
            _budget(),
        )
    )
    assert timeout_result.error is not None
    assert timeout_result.error.error_type == "timeout"


@pytest.mark.asyncio
async def test_semantic_failure_is_reported_before_policy_or_handler() -> None:
    called = False

    async def handler(_arguments: _Input, _state: AgentState) -> dict[str, Any]:
        nonlocal called
        called = True
        return {}

    def reject(_arguments: BaseModel, _state: AgentState) -> list[str]:
        return ["bad value"]

    registry = ToolRegistry(runtime_registry=cast(Any, None))
    registry.register(_tool(handler, semantic_validator=reject))
    result = await ToolExecutor(
        tool_registry=registry,
        policy_engine=_Policy(True),
    ).execute_tool(
        LLMToolCall(id="semantic", name="test_tool", arguments={"value": 1}),
        _state(),
        _budget(),
    )

    assert result.error is not None
    assert result.error.error_type == "semantic_validation"
    assert called is False
