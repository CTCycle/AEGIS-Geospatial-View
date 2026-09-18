from __future__ import annotations

from typing import Any

import pytest

from server.domain.agent.capability_domains import CapabilityDomain
from server.domain.agent.capability_route import (
    AgentGoal,
    AgentPhase,
    AgentRunState,
    CapabilityRoute,
)
from server.domain.agent.decision import ResolvedLocation
from server.domain.agent.tool_result import ToolExecutionMetadata, ToolResult
from server.contracts.geospatial import (
    GeospatialProviderLayerDescriptor,
    GeospatialProviderLayersResponse,
)
from server.services.agent.capability_execution import ToolExecutionContext
from server.services.agent.native_tools import register_agent_tools
from server.services.agent.native_tools import _execute_capability_handler
from server.services.agent.native_tools import _bind_execute_request
from server.services.agent.native_tools import _location_for_request
from server.services.agent.native_tools import _capability_semantic_validator
from server.services.agent.policy_engine import PolicyEngine
from server.services.agent.tool_definitions import ExecuteCapabilityInput
from server.services.agent.tool_definitions import ProviderLayerDiscoveryInput
from server.services.agent.tool_handlers.provider_layers import ProviderLayerToolHandler
from server.services.agent.tool_registry import ToolRegistry


###############################################################################
class FakeCapabilityRegistry:

    # -------------------------------------------------------------------------
    def get_capability(self, capability_id: str) -> dict[str, Any] | None:
        if capability_id == "places:hospitals":
            return {
                "id": capability_id,
                "name": "Hospitals",
                "provider": "overpass",
                "capabilityKind": "search-index",
            }
        return None

    # -------------------------------------------------------------------------
    def execution_contract(self, capability_id: str) -> dict[str, Any]:
        return {"capability_id": capability_id, "render_support": "vector"}

    # -------------------------------------------------------------------------
    def argument_schema(self, capability_id: str) -> dict[str, Any]:
        return {
            "type": "object",
            "additionalProperties": False,
            "required": ["query"],
            "properties": {"query": {"type": "string", "minLength": 1}},
        }

    # -------------------------------------------------------------------------
    def shortlist(self, **_kwargs: Any) -> list[dict[str, Any]]:
        return [self.get_capability("places:hospitals")]  # type: ignore[list-item]

    # -------------------------------------------------------------------------
    def list_basemaps(self) -> list[dict[str, Any]]:
        return [
            {"id": "osm_default"},
            {"id": "esri_world_imagery"},
            {"id": "osm_dark"},
        ]


###############################################################################
class FakeRuntimeRegistry:

    # -------------------------------------------------------------------------
    def is_enabled(self, _capability_id: str) -> bool:
        return True

    # -------------------------------------------------------------------------
    def access_available(self, _capability_id: str) -> bool:
        return True


###############################################################################
class FakeResolver:

    # -------------------------------------------------------------------------
    async def resolve_location_signals(self, _signals: Any, _memory: Any) -> Any:
        raise AssertionError("location resolution is not part of exposure tests")


###############################################################################
class FakeEvidenceRepository:
    pass


###############################################################################
class FakeCapabilityExecutionService:

    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        self.context: ToolExecutionContext | None = None
        self.request: ExecuteCapabilityInput | None = None

    # -------------------------------------------------------------------------
    async def execute_capability(
        self,
        _request: ExecuteCapabilityInput,
        context: ToolExecutionContext,
        *,
        location: ResolvedLocation | None = None,
    ) -> ToolResult:
        self.context = context
        self.request = _request
        return ToolResult(
            call_id=context.call_id,
            tool_name="execute_geospatial_capability",
            status="success",
            summary="ok",
            metadata=ToolExecutionMetadata(duration_ms=0),
        )


###############################################################################
def _registry() -> ToolRegistry:
    runtime = FakeRuntimeRegistry()
    registry = ToolRegistry(runtime_registry=runtime)  # type: ignore[arg-type]
    register_agent_tools(
        registry,
        capability_registry=FakeCapabilityRegistry(),  # type: ignore[arg-type]
        runtime_registry=runtime,  # type: ignore[arg-type]
        provider_registry=object(),  # type: ignore[arg-type]
        evidence_repository=FakeEvidenceRepository(),  # type: ignore[arg-type]
        location_resolver=FakeResolver(),  # type: ignore[arg-type]
        geospatial_api_service=object(),  # type: ignore[arg-type]
    )
    return registry


###############################################################################
def _state() -> AgentRunState:
    return AgentRunState(
        request_id="request-1",
        conversation_id="conversation-1",
        phase=AgentPhase.ROUTE_REQUEST,
        user_message="show hospitals",
    )


def test_apply_map_plan_describes_only_canonical_basemap_ids() -> None:
    registry = _registry()
    tool = registry.get("apply_map_plan")

    assert tool is not None
    assert "esri_world_imagery, osm_dark, osm_default" in tool.definition.description
    assert "Never invent, translate, or alias a basemap ID" in tool.definition.description


def test_map_only_routes_expose_map_preparation_without_data_execution() -> None:
    registry = _registry()
    state = _state()
    state.route = CapabilityRoute(
        primary_domain=CapabilityDomain.MAP_RENDERING,
        task_mode="execute",
        presentation="map",
        requires_location=True,
        capability_queries=["Vermont state map"],
    )
    state.phase = AgentPhase.BUILD_TOOL_CONTEXT
    state.capability_ids = ["places:hospitals"]
    state.location_refs["vermont, united states"] = ResolvedLocation(
        label="Vermont, United States",
        latitude=44.0,
        longitude=-72.7,
    )

    exposed = {tool.name for tool in registry.expose(state)}

    assert "apply_map_plan" in exposed
    assert "execute_geospatial_capability" not in exposed


def test_new_route_target_requires_location_resolution_even_with_active_map() -> None:
    registry = _registry()
    state = _state()
    state.route = CapabilityRoute(
        primary_domain=CapabilityDomain.MAP_STATE,
        task_mode="execute",
        presentation="map",
        requires_location=True,
        target_refs=["Salta, Argentina"],
    )
    state.phase = AgentPhase.BUILD_TOOL_CONTEXT
    state.active_map_session = object()  # type: ignore[assignment]
    state.location_refs = {
        "vermont, united states": ResolvedLocation(
            label="Vermont, United States", latitude=44.0, longitude=-72.7
        )
    }

    exposed = {tool.name for tool in registry.expose(state)}

    assert "resolve_geospatial_location" in exposed


###############################################################################
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


###############################################################################
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


def test_execute_binding_preserves_semantics_but_owns_scope_and_coordinates() -> None:
    state = _state()
    state.location_refs["zurich"] = ResolvedLocation(
        label="Zurich", latitude=47.3769, longitude=8.5417
    )
    state.goal = AgentGoal(
        goal="Show hospitals around Zurich tomorrow",
        task_mode="execute",
        presentation="map",
        operation="search",
        requires_location=True,
        target_ids=["zurich"],
        temporal_scope={
            "mode": "forecast",
            "start_time_iso": "2026-09-15T00:00:00Z",
            "end_time_iso": "2026-09-16T00:00:00Z",
        },
        spatial_scope=[
            {"kind": "radius", "relationship": "around", "distance_m": 5000}
        ],
        filters={"amenity": "hospital"},
    )
    bound = _bind_execute_request(
        ExecuteCapabilityInput(
            capability_id="places:hospitals",
            operation="provider_internal_operation",
            location_ref="zurich",
            bbox=[0, 0, 1, 1],
            radius_m=1,
            start_time_iso="1900-01-01T00:00:00Z",
            arguments={
                "latitude": 0,
                "longitude": 0,
                "bbox": [0, 0, 1, 1],
                "start_time_iso": "1900-01-01T00:00:00Z",
                "category": "hospital",
            },
            filters={"emergency": True},
        ),
        state,
    )

    assert bound.operation == "search"
    assert bound.location_ref == "zurich"
    assert bound.radius_m == 5000
    assert bound.start_time_iso == "2026-09-15T00:00:00Z"
    assert bound.end_time_iso == "2026-09-16T00:00:00Z"
    assert bound.bbox is not None
    assert bound.bbox[0] < 8.5417 < bound.bbox[2]
    assert bound.bbox[1] < 47.3769 < bound.bbox[3]
    assert bound.arguments == {"category": "hospital", "live": True}
    assert bound.filters == {"amenity": "hospital", "emergency": True}


def test_execute_binding_lowers_administrative_scope_to_resolved_bbox() -> None:
    state = _state()
    state.location_refs["sicily"] = ResolvedLocation(
        label="Sicily",
        latitude=37.6,
        longitude=14.0,
        bbox=[11.4, 36.6, 15.7, 38.4],
    )
    state.goal = AgentGoal(
        goal="Show satellite imagery in Sicily",
        task_mode="execute",
        presentation="map",
        operation="show_basemap",
        requires_location=True,
        target_ids=["sicily"],
        spatial_scope=[{"kind": "administrative_geometry", "relationship": "in"}],
    )

    bound = _bind_execute_request(
        ExecuteCapabilityInput(
            capability_id="esri_world_imagery",
            location_ref="sicily",
            bbox=[-180, -90, 180, 90],
        ),
        state,
    )

    assert bound.bbox == [11.4, 36.6, 15.7, 38.4]


def test_goal_target_reference_is_required_and_cannot_be_replaced() -> None:
    state = _state()
    state.goal = AgentGoal(
        goal="Show hospitals around Zurich",
        task_mode="execute",
        presentation="text",
        operation="search",
        requires_location=True,
        target_ids=["zurich"],
    )

    errors = _capability_semantic_validator(
        ExecuteCapabilityInput(
            capability_id="places:hospitals",
            location_ref="rome",
        ),
        state,
    )

    assert errors == [
        "location_ref must match an exact target in the validated goal; "
        "another geography will not be substituted."
    ]


def test_manifest_argument_schema_is_checked_before_execution() -> None:
    state = _state()
    state.capability_ids = ["places:hospitals"]

    errors = _capability_semantic_validator(
        ExecuteCapabilityInput(
            capability_id="places:hospitals",
            arguments={"query": "", "unexpected": True},
        ),
        state,
        capability_registry=FakeCapabilityRegistry(),  # type: ignore[arg-type]
    )

    assert errors == [
        "arguments.unexpected: additional property is not allowed.",
        "arguments.query: string is too short.",
    ]


###############################################################################
def _route() -> CapabilityRoute:
    return CapabilityRoute(
        primary_domain=CapabilityDomain.DATA_RETRIEVAL,
        task_mode="execute",
        presentation="both",
        requires_location=True,
        capability_queries=["hospitals"],
    )


###############################################################################
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
        "resolve_geospatial_location",
        "describe_geospatial_capability",
    ]

    state.location_refs["zurich"] = ResolvedLocation(
        label="Zurich",
        latitude=47.3769,
        longitude=8.5417,
    )
    assert [tool.name for tool in registry.expose(state)] == [
        "describe_geospatial_capability",
        "execute_geospatial_capability",
        "apply_map_plan",
    ]

    state.evidence_refs.append("evidence-1")
    assert {
        tool.name for tool in registry.expose(state)
    } == {
        "describe_geospatial_capability",
        "execute_geospatial_capability",
        "inspect_evidence",
        "transform_evidence",
        "apply_map_plan",
    }


###############################################################################
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


###############################################################################
def test_map_plan_is_not_exposed_for_text_only_routes() -> None:
    registry = _registry()
    state = _state()
    state.route = _route().model_copy(update={"presentation": "text"})
    state.phase = AgentPhase.BUILD_TOOL_CONTEXT
    state.capability_ids = ["places:hospitals"]
    state.location_refs["zurich"] = ResolvedLocation(
        label="Zurich", latitude=47.3769, longitude=8.5417
    )

    assert "apply_map_plan" not in {
        tool.name for tool in registry.expose(state)
    }


###############################################################################
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


def test_policy_rejects_capability_execution_on_map_only_routes() -> None:
    registry = _registry()
    state = _state()
    state.route = CapabilityRoute(
        primary_domain=CapabilityDomain.MAP_RENDERING,
        task_mode="execute",
        presentation="map",
        requires_location=True,
    )
    state.phase = AgentPhase.BUILD_TOOL_CONTEXT
    state.capability_ids = ["places:hospitals"]
    tool = registry.get("execute_geospatial_capability")
    assert tool is not None
    policy = PolicyEngine(
        location_resolver=FakeResolver(),  # type: ignore[arg-type]
        capability_registry=FakeCapabilityRegistry(),  # type: ignore[arg-type]
        runtime_registry=FakeRuntimeRegistry(),  # type: ignore[arg-type]
    )

    rejected = policy.authorize(
        tool,
        ExecuteCapabilityInput(capability_id="places:hospitals"),
        state,
    )

    assert rejected.allowed is False
    assert rejected.metadata["code"] == "route_domain_mismatch"


###############################################################################
def test_location_reference_never_falls_back_to_another_resolved_location() -> None:
    state = _state()
    state.location_refs = {
        "rome": ResolvedLocation(label="Rome", latitude=41.9, longitude=12.5),
        "zurich": ResolvedLocation(
            label="Zurich", latitude=47.3769, longitude=8.5417
        ),
    }

    missing = ExecuteCapabilityInput(
        capability_id="places:hospitals",
        location_ref="lugano",
    )
    explicit = ExecuteCapabilityInput(
        capability_id="places:hospitals",
        location_ref="zurich",
    )

    assert _location_for_request(missing, state) is None
    assert _location_for_request(explicit, state) == state.location_refs["zurich"]
    assert _location_for_request(
        ExecuteCapabilityInput(capability_id="places:hospitals"), state
    ) is None


###############################################################################
class _FakeProviderLayerService:

    def __init__(self) -> None:
        self.limit: int | None = None

    async def list_provider_layers(self, provider_id: str, **kwargs: Any) -> GeospatialProviderLayersResponse:
        self.limit = int(kwargs["limit"])
        return GeospatialProviderLayersResponse(
            provider=provider_id,
            layers=[
                GeospatialProviderLayerDescriptor(
                    provider=provider_id,
                    layer_id=f"layer-{index}",
                    title=f"Layer {index}",
                    rendering_mode="raster",
                    source_protocol="wms",
                    data_format="image/png",
                    geometry_type="raster",
                )
                for index in range(3)
            ],
        )


class _FakeEvidenceStore:

    def __init__(self) -> None:
        self.payload: Any = None

    def create(self, **kwargs: Any) -> Any:
        self.payload = kwargs
        return type("Evidence", (), {"evidence_id": "evidence-provider-layers"})()


def test_provider_layer_discovery_is_only_exposed_for_provider_route() -> None:
    registry = _registry()
    state = _state()
    state.route = CapabilityRoute(
        primary_domain=CapabilityDomain.PROVIDER_DISCOVERY,
        task_mode="execute",
        presentation="text",
        requires_location=False,
        capability_queries=["obscure layer"],
    )
    state.phase = AgentPhase.BUILD_TOOL_CONTEXT

    assert {
        tool.name for tool in registry.expose(state)
    } == {
        "discover_geospatial_capabilities",
        "discover_geospatial_provider_layers",
    }


@pytest.mark.asyncio
async def test_provider_layer_discovery_uses_bounded_pagination_and_evidence() -> None:
    provider_service = _FakeProviderLayerService()
    evidence_store = _FakeEvidenceStore()
    handler = ProviderLayerToolHandler(
        geospatial_api_service=provider_service,  # type: ignore[arg-type]
        evidence_repository=evidence_store,  # type: ignore[arg-type]
    )
    state = _state()
    state.run_id = "run-1"

    result = await handler.discover(
        ProviderLayerDiscoveryInput(
            provider_id="gibs",
            cursor="1",
            limit=1,
        ),
        state,
    )

    assert result.status == "success"
    assert result.data["layers"][0]["layer_id"] == "layer-1"  # type: ignore[index]
    assert result.data["next_cursor"] == "2"  # type: ignore[index]
    assert result.evidence_refs == ["evidence-provider-layers"]
    assert state.evidence_refs == ["evidence-provider-layers"]
    assert provider_service.limit == 250
    assert evidence_store.payload["run_id"] == "run-1"
