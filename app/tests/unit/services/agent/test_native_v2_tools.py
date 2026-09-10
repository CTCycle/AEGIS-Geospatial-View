from __future__ import annotations

from typing import Any

import pytest

from server.domain.agent.capability_domains import CapabilityDomain
from server.domain.agent.capability_route import AgentPhase, AgentState, CapabilityRoute
from server.domain.agent.decision import ResolvedLocation
from server.domain.agent.tool_result import ToolExecutionMetadata, ToolResult
from server.services.agent.capability_execution import ToolExecutionContext
from server.services.agent.native_v2_tools import register_native_v2_tools
from server.services.agent.native_v2_tools import _execute_capability_handler
from server.services.agent.policy_engine import PolicyEngine
from server.services.agent.tool_definitions import ExecuteCapabilityInput
from server.services.agent.tool_registry import ToolRegistry


class FakeCapabilityRegistry:
    def get_capability(self, capability_id: str) -> dict[str, Any] | None:
        if capability_id == "places:hospitals":
            return {
                "id": capability_id,
                "name": "Hospitals",
                "provider": "overpass",
                "capabilityKind": "search-index",
            }
        return None

    def execution_contract(self, capability_id: str) -> dict[str, Any]:
        return {"capability_id": capability_id, "render_support": "vector"}

    def shortlist(self, **_kwargs: Any) -> list[dict[str, Any]]:
        return [self.get_capability("places:hospitals")]  # type: ignore[list-item]


class FakeRuntimeRegistry:
    def is_enabled(self, _capability_id: str) -> bool:
        return True

    def access_available(self, _capability_id: str) -> bool:
        return True


class FakeResolver:
    async def resolve_location_signals(self, _signals: Any, _memory: Any) -> Any:
        raise AssertionError("location resolution is not part of exposure tests")


class FakeEvidenceRepository:
    pass


class FakeCapabilityExecutionService:
    def __init__(self) -> None:
        self.context: ToolExecutionContext | None = None

    async def execute_capability(
        self,
        _request: ExecuteCapabilityInput,
        context: ToolExecutionContext,
        *,
        location: ResolvedLocation | None = None,
    ) -> ToolResult:
        self.context = context
        return ToolResult(
            call_id=context.call_id,
            tool_name="execute_geospatial_capability",
            status="success",
            summary="ok",
            metadata=ToolExecutionMetadata(duration_ms=0),
        )


def _registry() -> ToolRegistry:
    runtime = FakeRuntimeRegistry()
    registry = ToolRegistry(runtime_registry=runtime)  # type: ignore[arg-type]
    register_native_v2_tools(
        registry,
        capability_registry=FakeCapabilityRegistry(),  # type: ignore[arg-type]
        runtime_registry=runtime,  # type: ignore[arg-type]
        provider_registry=object(),  # type: ignore[arg-type]
        evidence_repository=FakeEvidenceRepository(),  # type: ignore[arg-type]
        location_resolver=FakeResolver(),  # type: ignore[arg-type]
    )
    return registry


def _state() -> AgentState:
    return AgentState(
        request_id="request-1",
        conversation_id="conversation-1",
        phase=AgentPhase.ROUTE_REQUEST,
        user_message="show hospitals",
    )


@pytest.mark.asyncio
async def test_capability_handler_uses_persisted_run_id_not_request_id() -> None:
    service = FakeCapabilityExecutionService()
    state = _state()
    state.run_id = "run-1"

    result = await _execute_capability_handler(service)(
        ExecuteCapabilityInput(capability_id="places:hospitals"),
        state,
    )

    assert result.status == "success"
    assert service.context is not None
    assert service.context.run_id == "run-1"
    assert service.context.run_id != state.request_id


@pytest.mark.asyncio
async def test_compatibility_state_has_no_foreign_run_id() -> None:
    service = FakeCapabilityExecutionService()
    state = _state()

    await _execute_capability_handler(service)(
        ExecuteCapabilityInput(capability_id="places:hospitals"),
        state,
    )

    assert service.context is not None
    assert service.context.run_id is None


def _route() -> CapabilityRoute:
    return CapabilityRoute(
        primary_domain=CapabilityDomain.DATA_RETRIEVAL,
        task_mode="execute",
        presentation="both",
        requires_location=True,
        capability_queries=["hospitals"],
    )


def test_route_tool_is_hidden_after_bootstrap_and_exposure_is_progressive() -> None:
    registry = _registry()
    state = _state()

    assert [tool.name for tool in registry.expose(state)] == ["route_request"]

    state.route = _route()
    state.phase = AgentPhase.BUILD_TOOL_CONTEXT
    assert {
        tool.name for tool in registry.expose(state)
    } == {"resolve_geospatial_location", "discover_geospatial_capabilities"}

    state.capability_ids = ["places:hospitals"]
    assert [tool.name for tool in registry.expose(state)] == [
        "resolve_geospatial_location"
    ]

    state.location_refs["zurich"] = ResolvedLocation(
        label="Zurich",
        latitude=47.3769,
        longitude=8.5417,
    )
    assert [tool.name for tool in registry.expose(state)] == [
        "execute_geospatial_capability",
        "apply_map_plan",
    ]

    state.evidence_refs.append("evidence-1")
    assert {
        tool.name for tool in registry.expose(state)
    } == {
        "execute_geospatial_capability",
        "inspect_evidence",
        "transform_evidence",
        "apply_map_plan",
    }


def test_capability_schema_is_specialized_to_validated_shortlist() -> None:
    registry = _registry()
    state = _state()
    state.route = _route()
    state.phase = AgentPhase.BUILD_TOOL_CONTEXT
    state.capability_ids = ["places:hospitals"]
    state.location_refs["zurich"] = ResolvedLocation(
        label="Zurich",
        latitude=47.3769,
        longitude=8.5417,
    )

    definition = next(
        tool
        for tool in registry.expose(state)
        if tool.name == "execute_geospatial_capability"
    )
    capability_schema = definition.parameters_json_schema["properties"][
        "capability_id"
    ]
    assert capability_schema["enum"] == ["places:hospitals"]


def test_policy_authorizes_typed_capability_calls_once_against_route_and_runtime() -> None:
    registry = _registry()
    state = _state()
    state.route = _route()
    state.phase = AgentPhase.BUILD_TOOL_CONTEXT
    state.capability_ids = ["places:hospitals"]
    tool = registry.get("execute_geospatial_capability")
    assert tool is not None
    policy = PolicyEngine(
        location_resolver=FakeResolver(),  # type: ignore[arg-type]
        capability_registry=FakeCapabilityRegistry(),  # type: ignore[arg-type]
        runtime_registry=FakeRuntimeRegistry(),  # type: ignore[arg-type]
    )

    allowed = policy.authorize(
        tool,
        ExecuteCapabilityInput(capability_id="places:hospitals"),
        state,
    )
    rejected = policy.authorize(
        tool,
        ExecuteCapabilityInput(capability_id="places:unknown"),
        state,
    )

    assert allowed.allowed is True
    assert rejected.allowed is False
    assert rejected.metadata["code"] == "capability_not_shortlisted"
