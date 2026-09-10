"""Typed native-v2 tool registrations used by the composed runtime."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from server.domain.agent.capability_domains import CapabilityDomain
from server.domain.agent.capability_route import AgentPhase, AgentState
from server.domain.agent.map_plan import MapPlan
from server.domain.agent.tool_result import (
    ToolExecutionError,
    ToolExecutionMetadata,
    ToolResult,
)
from server.domain.agent.tools import RegisteredTool
from server.domain.llm.types import LLMToolDefinition
from server.repositories.agent_evidence import AgentEvidenceRepository
from server.services.agent.capability_execution import (
    CapabilityExecutionService,
    ToolExecutionContext,
)
from server.services.agent.map_plan_service import MapPlanService
from server.services.agent.tool_definitions import (
    ApplyMapPlanInput,
    CapabilityDiscoveryInput,
    ExecuteCapabilityInput,
    InspectEvidenceInput,
    ResolveLocationInput,
    RouteRequestInput,
    TransformEvidenceInput,
)
from server.services.agent.tool_handlers.catalog import CatalogToolHandler
from server.services.agent.tool_handlers.evidence import EvidenceToolHandler
from server.services.agent.tool_handlers.location import LocationToolHandler
from server.services.agent.tool_registry import ToolRegistry
from server.services.geospatial.capability_registry import CapabilityRegistry
from server.services.geospatial.provider_registry import ProviderRegistry
from server.services.geospatial.runtime_registry import RuntimeRegistry
from server.services.agent.location_resolver import LocationResolver
from server.domain.agent.decision import ResolvedLocation


_MODEL_PHASE = frozenset({AgentPhase.BUILD_TOOL_CONTEXT})
_ROUTE_PHASE = frozenset({AgentPhase.ROUTE_REQUEST})
_MIXED = frozenset({CapabilityDomain.MIXED})
_DATA = frozenset({CapabilityDomain.DATA_RETRIEVAL, CapabilityDomain.SPATIAL_ANALYSIS})
_MAP = frozenset({CapabilityDomain.MAP_RENDERING, CapabilityDomain.MAP_STATE})


def register_native_v2_tools(
    registry: ToolRegistry,
    *,
    capability_registry: CapabilityRegistry,
    runtime_registry: RuntimeRegistry,
    provider_registry: ProviderRegistry,
    evidence_repository: AgentEvidenceRepository,
    location_resolver: LocationResolver,
) -> None:
    """Register the permanent model-facing native-v2 tool surface once."""

    capability_execution = CapabilityExecutionService(
        capability_registry=capability_registry,
        runtime_registry=runtime_registry,
        provider_registry=provider_registry,
        evidence_repository=evidence_repository,
    )
    map_plan = MapPlanService(
        capability_registry=capability_registry,
        evidence_repository=evidence_repository,
    )
    catalog = CatalogToolHandler(
        capability_registry=capability_registry,
        runtime_registry=runtime_registry,
    )
    evidence = EvidenceToolHandler(repository=evidence_repository)
    location = LocationToolHandler(resolver=location_resolver)

    registrations = (
        _registration(
            name="route_request",
            description="Select one bounded high-level AEGIS capability route.",
            input_model=RouteRequestInput,
            handler=_route_handler,
            domains=_MIXED,
            phases=_ROUTE_PHASE,
            visibility="internal",
            prerequisites=frozenset(),
            idempotent=True,
        ),
        _registration(
            name="resolve_geospatial_location",
            description="Resolve a user-requested geographic target.",
            input_model=ResolveLocationInput,
            handler=location.resolve,
            domains=frozenset({CapabilityDomain.PLACE_SEARCH}),
            phases=_MODEL_PHASE,
            visibility="model",
            prerequisites=frozenset(
                {"route", "location_required", "location_missing"}
            ),
            idempotent=False,
        ),
        _registration(
            name="discover_geospatial_capabilities",
            description="Discover eligible capabilities from the validated catalog.",
            input_model=CapabilityDiscoveryInput,
            handler=catalog.discover,
            domains=_MIXED,
            phases=_MODEL_PHASE,
            visibility="model",
            prerequisites=frozenset({"route", "capability_shortlist_missing"}),
            idempotent=True,
        ),
        _registration(
            name="execute_geospatial_capability",
            description="Execute one shortlisted geospatial capability.",
            input_model=ExecuteCapabilityInput,
            handler=_execute_capability_handler(capability_execution),
            domains=_MIXED,
            phases=_MODEL_PHASE,
            visibility="model",
            prerequisites=frozenset(
                {"route", "capability_shortlist", "location_if_required"}
            ),
            idempotent=False,
            semantic_validator=_capability_semantic_validator,
        ),
        _registration(
            name="inspect_evidence",
            description="Inspect bounded metadata or samples from stored evidence.",
            input_model=InspectEvidenceInput,
            handler=evidence.inspect,
            domains=_DATA,
            phases=_MODEL_PHASE,
            visibility="model",
            prerequisites=frozenset({"route", "evidence"}),
            idempotent=True,
        ),
        _registration(
            name="transform_evidence",
            description="Apply bounded declarative transformations to stored evidence.",
            input_model=TransformEvidenceInput,
            handler=evidence.transform,
            domains=_DATA,
            phases=_MODEL_PHASE,
            visibility="model",
            prerequisites=frozenset({"route", "evidence"}),
            idempotent=False,
            semantic_validator=_evidence_semantic_validator,
        ),
        _registration(
            name="apply_map_plan",
            description="Prepare a typed map candidate from validated evidence.",
            input_model=ApplyMapPlanInput,
            handler=_apply_map_plan_handler(map_plan),
            domains=_MAP,
            phases=_MODEL_PHASE,
            visibility="model",
            prerequisites=frozenset({"route", "location", "evidence"}),
            idempotent=False,
        ),
    )
    for tool in registrations:
        registry.register(tool)


def _registration(
    *,
    name: str,
    description: str,
    input_model: type[BaseModel],
    handler: Any,
    domains: frozenset[CapabilityDomain],
    phases: frozenset[AgentPhase],
    visibility: str,
    prerequisites: frozenset[str],
    idempotent: bool,
    semantic_validator: Any = None,
) -> RegisteredTool:
    return RegisteredTool(
        definition=LLMToolDefinition(
            name=name,
            description=description,
            parameters_json_schema=input_model.model_json_schema(),
        ),
        input_model=input_model,
        handler=handler,
        domains=domains,
        phases=phases,
        visibility=visibility,  # type: ignore[arg-type]
        prerequisites=prerequisites,
        timeout_key="tool_execution_seconds",
        idempotent=idempotent,
        result_normalizer=_normalize_result,
        semantic_validator=semantic_validator,
    )


def _execute_capability_handler(service: CapabilityExecutionService) -> Any:
    async def execute(request: ExecuteCapabilityInput, state: AgentState) -> ToolResult:
        location = _location_for_request(request, state)
        return await service.execute_capability(
            request,
            ToolExecutionContext(
                conversation_id=state.conversation_id,
                run_id=state.run_id,
            ),
            location=location,
        )

    return execute


def _location_for_request(
    request: ExecuteCapabilityInput, state: AgentState
) -> ResolvedLocation | None:
    requested = " ".join(str(request.location_ref or "").casefold().split())
    if requested:
        for key, location in state.location_refs.items():
            if " ".join(str(key).casefold().split()) == requested:
                return location
    if state.location_refs:
        return next(iter(state.location_refs.values()))
    if state.active_map_session is not None:
        return state.active_map_session.resolved_location
    return None


def _apply_map_plan_handler(service: MapPlanService) -> Any:
    async def apply(request: ApplyMapPlanInput, state: AgentState) -> ToolResult:
        plan = MapPlan.model_validate(request.model_dump(mode="python"))
        return await service.apply(
            plan,
            state,
            ToolExecutionContext(
                conversation_id=state.conversation_id,
                run_id=state.run_id,
            ),
        )

    return apply


async def _route_handler(_request: RouteRequestInput, _state: AgentState) -> ToolResult:
    return ToolResult(
        call_id="handler-call",
        tool_name="route_request",
        status="failed",
        summary="Route selection is handled by the loop bootstrap.",
        error=ToolExecutionError(
            error_type="state_conflict",
            code="route_bootstrap_only",
            message="Route selection is handled by the loop bootstrap.",
            retryable=False,
            recovery="terminal",
        ),
        metadata=ToolExecutionMetadata(duration_ms=0),
    )


def _normalize_result(value: Any, call_id: str) -> ToolResult:
    if not isinstance(value, ToolResult):
        raise TypeError("Native-v2 handlers must return ToolResult.")
    return value.model_copy(update={"call_id": call_id})


def _capability_semantic_validator(
    request: ExecuteCapabilityInput, state: AgentState
) -> list[str]:
    if state.capability_ids and request.capability_id not in state.capability_ids:
        return ["capability_id is outside the validated route shortlist."]
    return []


def _evidence_semantic_validator(
    request: Any, state: AgentState
) -> list[str]:
    refs = list(getattr(request, "evidence_ref", None) and [request.evidence_ref] or [])
    refs.extend(getattr(request, "evidence_refs", []) or [])
    missing = [str(ref) for ref in refs if str(ref) not in state.evidence_refs]
    return [f"Unknown evidence reference: {ref}." for ref in missing[:8]]


__all__ = ["register_native_v2_tools"]
