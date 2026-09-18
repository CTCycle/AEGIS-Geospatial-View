from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest
from pydantic import BaseModel, ConfigDict

from server.domain.agent.capability_domains import CapabilityDomain
from server.domain.agent.capability_route import (
    AgentPhase,
    AgentRunState,
    CapabilityRoute,
)
from server.domain.agent.reliability import (
    AgentExecutionBudget,
    ExecutionBudgetExceeded,
)
from server.domain.agent.tool_result import ToolExecutionMetadata, ToolResult
from server.domain.agent.tools import RegisteredTool
from server.domain.llm.types import LLMToolCall, LLMToolDefinition
from server.services.agent.native_tools import (  # pyright: ignore[reportPrivateUsage]
    _capability_semantic_validator,
)
from server.services.agent.tool_definitions import ExecuteCapabilityInput
from server.services.agent.tool_executor import ToolExecutor
from server.services.agent.tool_registry import ToolRegistry


###############################################################################
class _Input(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: int


class _ManifestInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: int
    arguments: dict[str, Any] = {}


###############################################################################
class _Policy:

    # -------------------------------------------------------------------------
    def __init__(self, allowed: bool = True) -> None:
        self.allowed = allowed

    # -------------------------------------------------------------------------
    def authorize(self, _tool: RegisteredTool, _arguments: BaseModel, _state: AgentRunState):
        return cast(Any, type("Authorization", (), {"allowed": self.allowed, "reason": "blocked"})())


###############################################################################
def _state() -> AgentRunState:
    return AgentRunState(
        request_id="request-1",
        conversation_id="conversation-1",
        phase=AgentPhase.MODEL_STEP,
        user_message="Use the tool.",
    )


###############################################################################
def _budget() -> AgentExecutionBudget:
    return AgentExecutionBudget(total_seconds=5.0)


###############################################################################
def _tool(
    handler: Any,
    *,
    name: str = "test_tool",
    domains: frozenset[CapabilityDomain] | None = None,
    semantic_validator: Any | None = None,
    argument_schema_provider: Any | None = None,
    input_model: type[BaseModel] = _Input,
) -> RegisteredTool:
    def normalize(value: Any, call_id: str) -> ToolResult:
        return ToolResult(
            call_id=call_id,
            tool_name=name,
            status="success",
            summary=str(value),
            metadata=ToolExecutionMetadata(duration_ms=0),
        )

    return RegisteredTool(
        definition=LLMToolDefinition(
            name=name,
            description="Test tool",
            parameters_json_schema=input_model.model_json_schema(),
        ),
        input_model=input_model,
        handler=handler,
        domains=domains or frozenset({CapabilityDomain.DATA_RETRIEVAL}),
        phases=frozenset({AgentPhase.MODEL_STEP}),
        visibility="model",
        prerequisites=frozenset(),
        timeout_key="tool_execution_seconds",
        idempotent=True,
        result_normalizer=normalize,
        semantic_validator=semantic_validator,
        argument_schema_provider=argument_schema_provider,
    )


###############################################################################
def test_executor_validates_once_and_normalizes_success() -> None:
    calls: list[int] = []

    async def handler(arguments: _Input, _state: AgentRunState) -> dict[str, Any]:
        calls.append(arguments.value)
        return {"value": arguments.value}

    registry = ToolRegistry(runtime_registry=cast(Any, None))
    registry.register(_tool(handler))
    state = _state()
    result = asyncio.run(
        ToolExecutor(tool_registry=registry).execute_tool(
            LLMToolCall(id="call-1", name="test_tool", arguments={"value": 3}),
            state,
            _budget(),
        )
    )

    assert result.status == "success"
    assert calls == [3]
    assert state.tool_results == [result]
    assert state.tool_trace[0]["boundary"] == "tool_executor"


def test_mixed_domain_tool_is_authorized_for_a_mixed_map_data_route() -> None:
    async def handler(arguments: _Input, _state: AgentRunState) -> dict[str, Any]:
        return {"value": arguments.value}

    registry = ToolRegistry(runtime_registry=cast(Any, None))
    registry.register(
        _tool(
            handler,
            domains=frozenset({CapabilityDomain.MIXED}),
        )
    )
    state = _state()
    state.route = CapabilityRoute(
        primary_domain=CapabilityDomain.MAP_RENDERING,
        secondary_domains=[CapabilityDomain.DATA_RETRIEVAL],
        task_mode="execute",
        presentation="map",
        requires_location=True,
    )

    result = asyncio.run(
        ToolExecutor(tool_registry=registry).execute_tool(
            LLMToolCall(id="mixed-route", name="test_tool", arguments={"value": 3}),
            state,
            _budget(),
        )
    )

    assert result.status == "success"


###############################################################################
def test_malformed_call_never_reaches_the_handler() -> None:
    calls: list[int] = []

    async def handler(_arguments: _Input, _state: AgentRunState) -> dict[str, Any]:
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


###############################################################################
def test_tool_budget_is_enforced_by_the_execution_boundary() -> None:
    async def handler(_arguments: _Input, _state: AgentRunState) -> dict[str, Any]:
        return {"ok": True}

    registry = ToolRegistry(runtime_registry=cast(Any, None))
    registry.register(_tool(handler))
    budget = _budget()
    budget.configure_limits(max_tool_calls=1)
    executor = ToolExecutor(tool_registry=registry)

    first = asyncio.run(
        executor.execute_tool(
            LLMToolCall(id="first", name="test_tool", arguments={"value": 1}),
            _state(),
            budget,
        )
    )

    assert first.status == "success"
    with pytest.raises(ExecutionBudgetExceeded) as error:
        asyncio.run(
            executor.execute_tool(
                LLMToolCall(id="second", name="test_tool", arguments={"value": 2}),
                _state(),
                budget,
            )
        )
    assert error.value.reason == "tool_budget_exhausted"
    assert budget.tool_calls == 1


###############################################################################
def test_schema_semantic_policy_and_timeout_failures_are_typed() -> None:
    async def handler(_arguments: _Input, _state: AgentRunState) -> dict[str, Any]:
        await asyncio.sleep(0.05)
        return {}

    def reject(_arguments: BaseModel, _state: AgentRunState) -> list[str]:
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
    assert schema_result.data is not None
    correction = schema_result.data["correction"]
    assert correction["tool_name"] == "test_tool"
    assert correction["canonical_arguments"] == {}
    assert correction["required"] == ["value"]
    assert correction["validation_errors"]
    assert policy_result.error is not None
    assert policy_result.error.error_type == "policy_rejection"

    timeout_registry = ToolRegistry(runtime_registry=cast(Any, None))
    timeout_registry.register(_tool(handler))
    timeout_budget = _budget()
    timeout_result = asyncio.run(
        ToolExecutor(tool_registry=timeout_registry, timeout_seconds=0.01).execute_tool(
            LLMToolCall(id="timeout", name="test_tool", arguments={"value": 1}),
            _state(),
            timeout_budget,
        )
    )
    assert timeout_result.error is not None
    assert timeout_result.error.error_type == "timeout"
    assert [item.stage for item in timeout_budget.observations] == ["tool_execution"]

    map_registry = ToolRegistry(runtime_registry=cast(Any, None))
    map_registry.register(_tool(handler, name="apply_map_plan"))
    map_budget = _budget()
    map_budget.stage_limits["map_assembly"] = 0.01
    map_result = asyncio.run(
        ToolExecutor(tool_registry=map_registry, timeout_seconds=0.05).execute_tool(
            LLMToolCall(id="map-timeout", name="apply_map_plan", arguments={"value": 1}),
            _state(),
            map_budget,
        )
    )
    assert map_result.error is not None
    assert map_result.error.error_type == "timeout"
    assert [item.stage for item in map_budget.observations] == ["map_assembly"]


def test_manifest_validation_correction_contains_bounded_applicable_schema() -> None:
    calls: list[int] = []

    async def handler(arguments: _Input, _state: AgentRunState) -> dict[str, Any]:
        calls.append(arguments.value)
        return {"value": arguments.value}

    manifest_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["query"],
        "properties": {"query": {"type": "string", "minLength": 1}},
    }

    def reject(_arguments: BaseModel, _state: AgentRunState) -> list[str]:
        return ["arguments.query: required value is missing."]

    registry = ToolRegistry(runtime_registry=cast(Any, None))
    registry.register(
        _tool(
            handler,
            semantic_validator=reject,
            argument_schema_provider=lambda _arguments, _state: manifest_schema,
            input_model=_ManifestInput,
        )
    )
    result = asyncio.run(
        ToolExecutor(tool_registry=registry).execute_tool(
            LLMToolCall(
                id="manifest-schema",
                name="test_tool",
                arguments={
                    "value": 3,
                    "arguments": {"unexpected": "discard"},
                },
            ),
            _state(),
            _budget(),
        )
    )

    assert result.error is not None
    assert result.error.error_type == "semantic_validation"
    assert calls == []
    correction = result.data["correction"]  # type: ignore[index]
    assert correction["applicable_schema"] == manifest_schema
    assert correction["canonical_arguments"]["arguments"] == {}
    assert len(correction["validation_errors"]) == 1


def test_execute_capability_accepts_route_temporal_hint() -> None:
    calls: list[ExecuteCapabilityInput] = []

    async def handler(
        arguments: ExecuteCapabilityInput, _state: AgentRunState
    ) -> dict[str, Any]:
        calls.append(arguments)
        return {"ok": True}

    registry = ToolRegistry(runtime_registry=cast(Any, None))
    registry.register(
        _tool(
            handler,
            name="execute_geospatial_capability",
            input_model=ExecuteCapabilityInput,
        )
    )
    result = asyncio.run(
        ToolExecutor(tool_registry=registry).execute_tool(
            LLMToolCall(
                id="temporal-hint",
                name="execute_geospatial_capability",
                arguments={
                    "capability_id": "openmeteo_weather_forecast",
                    "location_ref": "rome",
                    "operation": "forecast",
                    "temporal_mode": "current",
                },
            ),
            _state(),
            _budget(),
        )
    )

    assert result.status == "success"
    assert [item.temporal_mode for item in calls] == ["current"]


def test_exclusive_radius_constraint_rejects_before_handler_execution() -> None:
    calls: list[int] = []
    manifest_schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "radius_m": {"type": "number", "exclusiveMinimum": 0},
        },
    }

    async def handler(
        _arguments: ExecuteCapabilityInput, _state: AgentRunState
    ) -> dict[str, Any]:
        calls.append(1)
        return {"ok": True}

    class _CapabilityRegistry:
        def argument_schema(self, _capability_id: str) -> dict[str, Any]:
            return manifest_schema

    def provide_schema(
        _arguments: BaseModel, _state: AgentRunState
    ) -> dict[str, Any]:
        return manifest_schema

    def validate(arguments: BaseModel, _state: AgentRunState) -> list[str]:
        return _capability_semantic_validator(
            cast(ExecuteCapabilityInput, arguments),
            _state,
            capability_registry=cast(Any, _CapabilityRegistry()),
        )

    registry = ToolRegistry(runtime_registry=cast(Any, None))
    registry.register(
        _tool(
            handler,
            name="execute_geospatial_capability",
            semantic_validator=validate,
            argument_schema_provider=provide_schema,
            input_model=ExecuteCapabilityInput,
        )
    )
    result = asyncio.run(
        ToolExecutor(tool_registry=registry).execute_tool(
            LLMToolCall(
                id="exclusive-radius",
                name="execute_geospatial_capability",
                arguments={"capability_id": "radius-test", "arguments": {"radius_m": 0}},
            ),
            _state(),
            _budget(),
        )
    )

    assert result.error is not None
    assert result.error.error_type == "semantic_validation"
    assert result.error.validation_errors[0].path == "$"
    assert "exclusive minimum" in result.error.validation_errors[0].message
    assert calls == []


###############################################################################
@pytest.mark.asyncio
async def test_semantic_failure_is_reported_before_policy_or_handler() -> None:
    called = False

    async def handler(_arguments: _Input, _state: AgentRunState) -> dict[str, Any]:
        nonlocal called
        called = True
        return {}

    def reject(_arguments: BaseModel, _state: AgentRunState) -> list[str]:
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
