from __future__ import annotations

from typing import Any, cast

import pytest
from pydantic import BaseModel, ValidationError

from server.domain.agent.capability_route import (
    AgentPhase,
    AgentState,
    CapabilityRoute,
)
from server.domain.agent.capability_domains import CapabilityDomain
from server.domain.agent.tool_result import ToolExecutionMetadata, ToolResult
from server.domain.agent.tools import RegisteredTool
from server.services.agent.tool_definitions import (
    ApplyMapPlanInput,
    ExecuteCapabilityInput,
    ResolveLocationInput,
)
from server.services.agent.tool_registry import ToolRegistry
from server.services.llm.types import LLMToolDefinition


###############################################################################
async def _handler(_arguments: BaseModel, _state: AgentState) -> dict[str, Any]:
    return {"ok": True}


###############################################################################
def _result(_value: Any, call_id: str) -> ToolResult:
    return ToolResult(
        call_id=call_id,
        tool_name="test",
        status="success",
        summary="ok",
        metadata=ToolExecutionMetadata(duration_ms=0),
    )


###############################################################################
def _registered(
    name: str,
    input_model: type[BaseModel],
    *,
    phase: AgentPhase,
    prerequisites: frozenset[str] = frozenset(),
) -> RegisteredTool:
    return RegisteredTool(
        definition=LLMToolDefinition(
            name=name,
            description=name,
            parameters_json_schema=input_model.model_json_schema(),
        ),
        input_model=input_model,
        handler=_handler,
        domains=frozenset({CapabilityDomain.DATA_RETRIEVAL}),
        phases=frozenset({phase}),
        visibility="model",
        prerequisites=prerequisites,
        timeout_key="tool_execution_seconds",
        idempotent=True,
        result_normalizer=_result,
    )


###############################################################################
def _state(phase: AgentPhase, *, capability_ids: list[str] | None = None) -> AgentState:
    return AgentState(
        request_id="request-1",
        conversation_id="conversation-1",
        phase=phase,
        user_message="Find data.",
        capability_ids=capability_ids or [],
    )


###############################################################################
def test_exposure_is_phase_and_prerequisite_bound() -> None:
    registry = ToolRegistry(runtime_registry=cast(Any, None))
    registry.register(
        _registered(
            "route_request",
            ResolveLocationInput,
            phase=AgentPhase.ROUTE_REQUEST,
        )
    )
    registry.register(
        _registered(
            "execute_geospatial_capability",
            ExecuteCapabilityInput,
            phase=AgentPhase.MODEL_STEP,
            prerequisites=frozenset({"route", "capability_shortlist"}),
        )
    )
    registry.register(
        _registered(
            "apply_map_plan",
            ApplyMapPlanInput,
            phase=AgentPhase.MODEL_STEP,
            prerequisites=frozenset({"route", "evidence"}),
        )
    )

    assert [item.name for item in registry.expose(_state(AgentPhase.ROUTE_REQUEST))] == [
        "route_request"
    ]
    assert registry.expose(_state(AgentPhase.MODEL_STEP)) == []

    state = _state(AgentPhase.MODEL_STEP, capability_ids=["traffic", "weather"])
    state.route = CapabilityRoute(
        primary_domain=CapabilityDomain.DATA_RETRIEVAL,
        task_mode="execute",
        presentation="map",
        requires_location=True,
    )
    state.evidence_refs = ["evidence:1"]
    exposed = registry.expose(state)
    assert [item.name for item in exposed] == [
        "execute_geospatial_capability",
        "apply_map_plan",
    ]
    execute_schema = exposed[0].parameters_json_schema
    assert execute_schema["properties"]["capability_id"]["enum"] == [
        "traffic",
        "weather",
    ]


###############################################################################
def test_typed_tool_inputs_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        ResolveLocationInput.model_validate({"query": "Zurich", "extra": True})
    assert ApplyMapPlanInput.model_json_schema()["additionalProperties"] is False
