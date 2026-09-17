"""Typed native tool registrations used by the composed runtime."""

from __future__ import annotations

import math
from typing import Any

from pydantic import BaseModel

from server.common.typing import is_json_array
from server.domain.agent.capability_domains import CapabilityDomain
from server.domain.agent.capability_route import AgentPhase, AgentRunState
from server.domain.agent.map_plan import MapPlan
from server.domain.agent.tool_result import (
    ToolExecutionError,
    ToolExecutionMetadata,
    ToolResult,
)
from server.domain.agent.tools import RegisteredTool
from server.domain.llm.types import LLMToolDefinition
from server.repositories.agent_evidence import AgentEvidenceRepository
from server.repositories.chat_history import ChatHistoryRepository
from server.services.agent.capability_execution import (
    CapabilityExecutionService,
    ToolExecutionContext,
)
from server.services.agent.map_plan_service import MapPlanService
from server.services.agent.tool_definitions import (
    ApplyMapPlanInput,
    CapabilityDiscoveryInput,
    DescribeCapabilityInput,
    ExecuteCapabilityInput,
    InspectEvidenceInput,
    ProviderLayerDiscoveryInput,
    ResolveLocationInput,
    RouteRequestInput,
    TransformEvidenceInput,
    SearchConversationHistoryInput,
)
from server.services.agent.tool_handlers.catalog import CatalogToolHandler
from server.services.agent.tool_handlers.evidence import EvidenceToolHandler
from server.services.agent.tool_handlers.location import LocationToolHandler
from server.services.agent.tool_handlers.provider_layers import ProviderLayerToolHandler
from server.services.agent.tool_handlers.history import HistoryToolHandler
from server.services.agent.tool_registry import ToolRegistry
from server.services.geospatial.capability_registry import CapabilityRegistry
from server.services.geospatial.provider_registry import ProviderRegistry
from server.services.geospatial.runtime_registry import RuntimeRegistry
from server.services.agent.location_resolver import LocationResolver
from server.domain.agent.decision import ResolvedLocation
from server.common.identifiers import normalize_target_key


_MODEL_PHASE = frozenset({AgentPhase.BUILD_TOOL_CONTEXT})
_ROUTE_PHASE = frozenset({AgentPhase.ROUTE_REQUEST})
_MIXED = frozenset({CapabilityDomain.MIXED})
_DATA = frozenset({CapabilityDomain.DATA_RETRIEVAL, CapabilityDomain.SPATIAL_ANALYSIS})
_MAP = frozenset({CapabilityDomain.MAP_RENDERING, CapabilityDomain.MAP_STATE})


###############################################################################
def _validated_basemap_ids(capability_registry: CapabilityRegistry) -> list[str]:
    """Return the exact canonical basemap IDs exposed by the active catalog."""

    return sorted(
        {
            str(item.get("id") or "").strip()
            for item in capability_registry.list_basemaps()
            if str(item.get("id") or "").strip()
        }
    )


###############################################################################
def register_agent_tools(
    registry: ToolRegistry,
    *,
    capability_registry: CapabilityRegistry,
    runtime_registry: RuntimeRegistry,
    provider_registry: ProviderRegistry,
    evidence_repository: AgentEvidenceRepository,
    location_resolver: LocationResolver,
    geospatial_api_service: Any,
    history_repository: ChatHistoryRepository | None = None,
) -> None:
    """Register the permanent model-facing native tool surface once."""

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
    provider_layers = ProviderLayerToolHandler(
        geospatial_api_service=geospatial_api_service,
        evidence_repository=evidence_repository,
    )
    history = (
        HistoryToolHandler(repository=history_repository)
        if history_repository is not None
        else None
    )
    basemap_ids = _validated_basemap_ids(capability_registry)
    basemap_catalog = ", ".join(basemap_ids) or "no basemap IDs"

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
            name="discover_geospatial_provider_layers",
            description=(
                "Discover bounded provider-native layer metadata for an explicitly "
                "routed provider when the manifest catalog is insufficient."
            ),
            input_model=ProviderLayerDiscoveryInput,
            handler=provider_layers.discover,
            domains=frozenset({CapabilityDomain.PROVIDER_DISCOVERY}),
            phases=_MODEL_PHASE,
            visibility="model",
            prerequisites=frozenset({"route", "provider_discovery_route"}),
            idempotent=True,
            semantic_validator=_provider_layer_semantic_validator,
        ),
        _registration(
            name="describe_geospatial_capability",
            description=(
                "Describe one shortlisted capability, including its execution "
                "contract and bounded argument schema."
            ),
            input_model=DescribeCapabilityInput,
            handler=catalog.describe,
            domains=_MIXED,
            phases=_MODEL_PHASE,
            visibility="model",
            prerequisites=frozenset({"route", "capability_shortlist"}),
            idempotent=True,
            semantic_validator=_describe_semantic_validator,
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
                {
                    "route",
                    "capability_shortlist",
                    "location_if_required",
                    "data_route",
                }
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
            description=(
                "Prepare a typed map candidate from validated location and evidence; "
                "the server supplies the catalog default basemap when a new map "
                "omits one. If setting a basemap, use only one of these exact "
                f"canonical catalog IDs: {basemap_catalog}. Never invent, "
                "translate, or alias a basemap ID; if the requested style is "
                "unsupported, leave the current map unchanged and report that. "
                "For add_evidence_layer, evidence_ref must be copied exactly "
                "from a prior successful evidence-producing tool result; never "
                "use a location_ref, place name, or capability ID as evidence. "
                "A location-only map uses set_viewport with fit_location and no "
                "evidence layer."
            ),
            input_model=ApplyMapPlanInput,
            handler=_apply_map_plan_handler(map_plan),
            domains=_MAP,
            phases=_MODEL_PHASE,
            visibility="model",
            # A location-only map is a valid candidate: it can contain a
            # validated basemap and viewport without fabricating a data layer.
            prerequisites=frozenset({"route", "location", "map_presentation"}),
            idempotent=False,
        ),
    )
    if history is not None:
        registrations += (
            _registration(
                name="search_conversation_history",
                description=(
                    "Search bounded original user and assistant messages in the "
                    "active conversation. Results are paged and never cross "
                    "conversation boundaries."
                ),
                input_model=SearchConversationHistoryInput,
                handler=history.search_conversation_history,
                domains=_MIXED,
                phases=_MODEL_PHASE,
                visibility="model",
                prerequisites=frozenset({"route"}),
                idempotent=True,
            ),
        )
    for tool in registrations:
        registry.register(tool)


###############################################################################
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


###############################################################################
def _execute_capability_handler(service: CapabilityExecutionService) -> Any:
    async def execute(request: ExecuteCapabilityInput, state: AgentRunState) -> ToolResult:
        bound_request = _bind_execute_request(request, state)
        location = _location_for_request(bound_request, state)
        return await service.execute_capability(
            bound_request,
            ToolExecutionContext(
                conversation_id=state.conversation_id,
                run_id=state.run_id,
            ),
            location=location,
        )

    return execute


def _bind_execute_request(
    request: ExecuteCapabilityInput, state: AgentRunState
) -> ExecuteCapabilityInput:
    """Bind model intent to server-owned route, scope, and location values.

    The model may select a capability and provide user-semantic filters, but
    it must not be able to move an execution to a different resolved target or
    smuggle provider geometry/time arguments through the generic arguments
    object. The route compiler is the source of truth once it exists.
    """

    goal = state.goal
    if goal is None:
        return request

    updates: dict[str, Any] = {
        "operation": goal.operation or request.operation,
        # Execute requests are evidence-producing operations.  Provider
        # adapters may expose a descriptor-only mode for catalog/UI calls,
        # but the native agent must obtain the bounded payload needed for
        # completion, inspection, and map rendering.
        "arguments": {**_user_arguments(request.arguments), "live": True},
        "filters": {**goal.filters, **request.filters},
        "bbox": None,
    }
    temporal = goal.temporal_scope
    if temporal:
        updates["start_time_iso"] = _optional_string(temporal.get("start_time_iso"))
        updates["end_time_iso"] = _optional_string(temporal.get("end_time_iso"))
        reference_time = _optional_string(temporal.get("reference_time_iso"))
        if reference_time:
            updates["arguments"] = {
                **updates["arguments"],
                "reference_time_iso": reference_time,
            }

    if not request.location_ref and len(goal.target_ids) == 1:
        updates["location_ref"] = goal.target_ids[0]

    bound = request.model_copy(update=updates)
    location = _location_for_request(bound, state)
    spatial = goal.spatial_scope[0] if goal.spatial_scope else {}
    distance_m = _positive_float(spatial.get("distance_m"))
    if distance_m is not None:
        bound = bound.model_copy(update={"radius_m": distance_m})
    if location is not None:
        radius = distance_m or bound.radius_m
        if radius is not None:
            bound = bound.model_copy(
                update={"bbox": _bbox_for_radius(location, radius)}
            )
        elif location.bbox:
            bound = bound.model_copy(update={"bbox": list(location.bbox)})
    return bound


def _user_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    """Keep semantic provider arguments while removing invariant aliases."""

    owned = {
        "bbox",
        "end",
        "end_time",
        "end_time_iso",
        "latitude",
        "location_ref",
        "location_refs",
        "longitude",
        "radius",
        "radius_m",
        "start",
        "start_time",
        "start_time_iso",
        "temporal_scope",
        "time",
    }
    return {
        key: value
        for key, value in arguments.items()
        if str(key).strip().casefold() not in owned
    }


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _positive_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def _bbox_for_radius(location: ResolvedLocation, radius_m: float) -> list[float]:
    """Create a bounded approximate bbox from a resolved point and radius."""

    latitude_delta = radius_m / 111_320.0
    longitude_scale = max(0.01, math.cos(math.radians(location.latitude)))
    longitude_delta = radius_m / (111_320.0 * longitude_scale)
    return [
        max(-180.0, location.longitude - longitude_delta),
        max(-90.0, location.latitude - latitude_delta),
        min(180.0, location.longitude + longitude_delta),
        min(90.0, location.latitude + latitude_delta),
    ]


###############################################################################
def _location_for_request(
    request: ExecuteCapabilityInput, state: AgentRunState
) -> ResolvedLocation | None:
    requested = normalize_target_key(str(request.location_ref or ""))
    goal_targets = {
        normalize_target_key(str(item))
        for item in (state.goal.target_ids if state.goal is not None else [])
        if normalize_target_key(str(item))
    }
    if goal_targets and requested not in goal_targets:
        return None
    if requested:
        for key, location in state.location_refs.items():
            if normalize_target_key(str(key)) == requested:
                return location
        return None
    if len(state.location_refs) > 1:
        return None
    if state.location_refs:
        return next(iter(state.location_refs.values()))
    if state.active_map_session is not None:
        return state.active_map_session.resolved_location
    return None


###############################################################################
def _apply_map_plan_handler(service: MapPlanService) -> Any:
    async def apply(request: ApplyMapPlanInput, state: AgentRunState) -> ToolResult:
        # A new map has no prior collection revision.  Bind this invariant on
        # the server so a model's speculative revision cannot reject a valid
        # first candidate; active-map updates still use the exact CAS revision.
        if state.active_map_session is None:
            request = request.model_copy(update={"expected_collection_revision": 0})
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


###############################################################################
async def _route_handler(_request: RouteRequestInput, _state: AgentRunState) -> ToolResult:
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


###############################################################################
def _normalize_result(value: Any, call_id: str) -> ToolResult:
    if not isinstance(value, ToolResult):
        raise TypeError("Native handlers must return ToolResult.")
    return value.model_copy(update={"call_id": call_id})


###############################################################################
def _capability_semantic_validator(
    request: ExecuteCapabilityInput, state: AgentRunState
) -> list[str]:
    if state.capability_ids and request.capability_id not in state.capability_ids:
        return ["capability_id is outside the validated route shortlist."]
    goal_targets = {
        normalize_target_key(str(item))
        for item in (state.goal.target_ids if state.goal is not None else [])
        if normalize_target_key(str(item))
    }
    requested_target = normalize_target_key(str(request.location_ref or ""))
    if requested_target and goal_targets and requested_target not in goal_targets:
        return [
            "location_ref must match an exact target in the validated goal; "
            "another geography will not be substituted."
        ]
    if request.location_ref:
        if _location_for_request(request, state) is None:
            return [
                "location_ref must match one exact resolved location reference; "
                "another location will not be substituted."
            ]
    elif len(state.location_refs) > 1:
        return [
            "location_ref is required when more than one resolved location is "
            "available."
        ]
    return []


###############################################################################
def _evidence_semantic_validator(
    request: Any, state: AgentRunState
) -> list[str]:
    refs = list(getattr(request, "evidence_ref", None) and [request.evidence_ref] or [])
    refs.extend(getattr(request, "evidence_refs", []) or [])
    missing = [str(ref) for ref in refs if str(ref) not in state.evidence_refs]
    return [f"Unknown evidence reference: {ref}." for ref in missing[:8]]


###############################################################################
def _provider_layer_semantic_validator(
    request: ProviderLayerDiscoveryInput, state: AgentRunState
) -> list[str]:
    allowed = state.policy_constraints.get("allowed_provider_ids")
    if is_json_array(allowed) and allowed:
        normalized = request.provider_id.casefold()
        permitted = {str(item).casefold() for item in allowed}
        if normalized not in permitted:
            return ["provider_id is outside the validated provider allowlist."]
    return []


###############################################################################
def _describe_semantic_validator(
    request: DescribeCapabilityInput, state: AgentRunState
) -> list[str]:
    if not state.capability_ids:
        return ["capability_id must be selected by the validated route first."]
    if request.capability_id not in state.capability_ids:
        return ["capability_id is outside the validated route shortlist."]
    return []


__all__ = ["register_agent_tools"]
