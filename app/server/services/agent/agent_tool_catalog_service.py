from __future__ import annotations

from server.common.typing import is_json_object, json_object

from typing import Any, cast

from server.domain.agent.catalog import (
    CATALOG_PAGE_LIMIT,
    CapabilityCatalogFilter,
    GeospatialCapabilityExecutionResult,
)
from server.domain.agent.decision import ClarificationRequest, ExecutionPlan, ResolvedLocation
from server.domain.agent.execution import AgentExecutionContext
from server.contracts.extraction import LocationSignal, TurnParseResult
from server.contracts.geospatial import MapSession, ProviderLayerSelection
from server.domain.agent.policies import ToolAuthorizationResult
from server.services.agent.location_resolver import LocationResolver
from server.services.agent.policy_engine import PolicyEngine
from server.services.agent.tool_registry import ToolRegistry
from server.services.geospatial.capability_registry import CapabilityRegistry
from server.services.geospatial.api_service import GeospatialApiService
from server.services.geospatial.manifest_loader import GeospatialManifestLoader
from server.services.geospatial.runtime_registry import RuntimeRegistry
from server.services.llm.types import LLMToolDefinition
from server.services.search.orchestrator import LocationSearchOrchestrator
from server.services.search.request_builder import RequestBuilder

###############################################################################
class AgentToolCatalogService:

    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        capability_registry: CapabilityRegistry | None = None,
        manifest_loader: GeospatialManifestLoader | None = None,
        runtime_registry: RuntimeRegistry,
        search_orchestrator: LocationSearchOrchestrator | None = None,
        request_builder: RequestBuilder | None = None,
        location_resolver: LocationResolver | None = None,
        tool_registry: ToolRegistry | None = None,
        policy_engine: PolicyEngine | None = None,
        geospatial_api_service: GeospatialApiService,
    ) -> None:
        self.capability_registry = capability_registry or CapabilityRegistry()
        self.manifest_loader = manifest_loader or GeospatialManifestLoader()
        self.runtime_registry = runtime_registry
        self.search_orchestrator = search_orchestrator
        self.request_builder = request_builder or RequestBuilder()
        self.location_resolver = location_resolver or LocationResolver()
        self.tool_registry = tool_registry
        self.policy_engine = policy_engine
        self.geospatial_api_service = geospatial_api_service

    # -------------------------------------------------------------------------
    def build_native_tools(
        self,
        context: AgentExecutionContext | None = None,
    ) -> list[LLMToolDefinition]:
        metadata = context.metadata if context is not None else {}
        allowed_tool_names = set(map(str, metadata.get("allowed_native_tools") or []))
        allowed_capability_ids = sorted(
            set(map(str, metadata.get("allowed_capability_ids") or []))
        )
        definitions = [
            LLMToolDefinition(
                name="list_geospatial_capabilities",
                description="List available geospatial capabilities with deterministic pagination and filters.",
                parameters_json_schema={
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "query": {"type": ["string", "null"]},
                        "category": {"type": ["string", "null"]},
                        "geometry_type": {"type": ["string", "null"]},
                        "bbox": {
                            "type": ["array", "null"],
                            "items": {"type": "number"},
                            "minItems": 4,
                            "maxItems": 4,
                        },
                        "limit": {"type": "integer", "minimum": 1, "maximum": CATALOG_PAGE_LIMIT},
                        "cursor": {"type": ["string", "null"]},
                    },
                },
            ),
            LLMToolDefinition(
                name="describe_geospatial_capability",
                description="Return full manifest metadata and executable argument schema for one capability.",
                parameters_json_schema={
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {"capability_id": {"type": "string"}},
                    "required": ["capability_id"],
                },
            ),
            LLMToolDefinition(
                name="execute_geospatial_capability",
                description="Execute a geospatial capability by stable manifest capability_id after schema validation.",
                parameters_json_schema={
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "capability_id": {"type": "string"},
                        "arguments": {"type": "object"},
                    },
                    "required": ["capability_id", "arguments"],
                },
            ),
            LLMToolDefinition(
                name="fetch_geospatial_provider_layers",
                description="Fetch normalized provider-native geospatial layers without returning raw provider XML.",
                parameters_json_schema={
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "provider_id": {
                            "type": "string",
                            "description": "Provider ID, for example gibs.",
                        },
                        "query": {
                            "type": ["string", "null"],
                            "description": "Optional search text for provider-native layers.",
                        },
                        "limit": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 250,
                            "default": 50,
                        },
                        "refresh": {
                            "type": "boolean",
                            "default": False,
                        },
                    },
                    "required": ["provider_id"],
                },
            ),
            LLMToolDefinition(
                name="render_geospatial_provider_layer",
                description="Render one provider-native layer descriptor into a normalized map session overlay.",
                parameters_json_schema={
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "provider_id": {"type": "string"},
                        "layer_id": {"type": "string"},
                        "time": {"type": ["string", "null"]},
                        "style": {"type": ["string", "null"]},
                        "format": {"type": ["string", "null"]},
                    },
                    "required": ["provider_id", "layer_id"],
                },
            ),
        ]
        if allowed_capability_ids:
            execute = next(
                item for item in definitions if item.name == "execute_geospatial_capability"
            )
            execute.parameters_json_schema["properties"]["capability_id"]["enum"] = (
                allowed_capability_ids
            )
        if allowed_tool_names:
            return [item for item in definitions if item.name in allowed_tool_names]
        return definitions

    # -------------------------------------------------------------------------
    def register_with(self, registry: ToolRegistry) -> None:
        for definition in self.build_native_tools():
            if definition.name == "list_geospatial_capabilities":
                registry.register_native_tool(definition, self._list_tool_handler)
            elif definition.name == "describe_geospatial_capability":
                registry.register_native_tool(definition, self._describe_tool_handler)
            elif definition.name == "execute_geospatial_capability":
                registry.register_native_tool(definition, self._execute_tool_handler)
            elif definition.name == "fetch_geospatial_provider_layers":
                registry.register_native_tool(definition, self._provider_layers_tool_handler)
            elif definition.name == "render_geospatial_provider_layer":
                registry.register_native_tool(definition, self._render_provider_layer_tool_handler)

    # -------------------------------------------------------------------------
    async def _list_tool_handler(
        self,
        arguments: dict[str, Any],
        context: AgentExecutionContext,
    ) -> dict[str, Any]:
        _ = context
        return self.list_geospatial_capabilities(CapabilityCatalogFilter(**arguments))

    # -------------------------------------------------------------------------
    async def _describe_tool_handler(
        self,
        arguments: dict[str, Any],
        context: AgentExecutionContext,
    ) -> dict[str, Any]:
        _ = context
        return self.describe_geospatial_capability(str(arguments["capability_id"]))

    # -------------------------------------------------------------------------
    async def _execute_tool_handler(
        self,
        arguments: dict[str, Any],
        context: AgentExecutionContext,
    ) -> dict[str, Any]:
        return dict(await self.execute_geospatial_capability(
            str(arguments["capability_id"]),
            dict(arguments.get("arguments") or {}),
            context=context,
        ))

    # -------------------------------------------------------------------------
    async def _provider_layers_tool_handler(
        self,
        arguments: dict[str, Any],
        context: AgentExecutionContext,
    ) -> dict[str, Any]:
        _ = context
        response = await self.geospatial_api_service.list_provider_layers(
            str(arguments["provider_id"]),
            query=arguments.get("query") if isinstance(arguments.get("query"), str) else None,
            limit=int(arguments.get("limit") or 50),
            refresh=bool(arguments.get("refresh", False)),
        )
        payload = response.model_dump(mode="json")
        if response.layers and self.search_orchestrator is not None:
            selected = response.layers[0]
            render_result = await self._render_provider_layer(
                {
                    "provider_id": selected.provider,
                    "layer_id": selected.layer_id,
                    "time": selected.default_time,
                },
                context,
            )
            if render_result.get("ok") is True:
                payload["selected_layer"] = selected.model_dump(mode="json")
                payload["map_session"] = render_result.get("map_session")
                payload["warnings"] = [
                    *list(payload.get("warnings") or []),
                    *list(render_result.get("warnings") or []),
                ]
        return payload

    # -------------------------------------------------------------------------
    async def _render_provider_layer_tool_handler(
        self,
        arguments: dict[str, Any],
        context: AgentExecutionContext,
    ) -> dict[str, Any]:
        return dict(await self._render_provider_layer(arguments, context))

    # -------------------------------------------------------------------------
    async def _render_provider_layer(
        self,
        arguments: dict[str, Any],
        context: AgentExecutionContext | None,
    ) -> GeospatialCapabilityExecutionResult:
        provider_id = str(arguments["provider_id"])
        layer_id = str(arguments["layer_id"])
        capability_id = f"{provider_id}:{layer_id}"
        if self.search_orchestrator is None:
            return self._error_result(
                capability_id=capability_id,
                arguments=arguments,
                operation="provider_error",
                code="provider_error",
                message="Search orchestrator is not configured for provider layer rendering.",
            )
        resolved_location = await self._resolve_location(arguments, context)
        if is_json_object(resolved_location) and resolved_location.get("error"):
            return cast(GeospatialCapabilityExecutionResult, resolved_location)
        if not isinstance(resolved_location, ResolvedLocation):
            return cast(GeospatialCapabilityExecutionResult, resolved_location)
        parsed_request = self._parsed_turn(context)
        plan = ExecutionPlan(
            state="map_search",
            mode="map",
            action_id=(
                parsed_request.normalized_action.action_id
                if parsed_request is not None
                else "provider_layer_render"
            ),
            basemap_id=parsed_request.requested_basemap if parsed_request is not None else None,
            overlay_ids=[],
        )
        request = self.request_builder.build_location_search_request(
            plan,
            resolved_location,
            turn_contract=parsed_request,
            active_visualization=(
                context.map_state.get("active_visualization")
                if context is not None and is_json_object(context.map_state)
                else None
            ),
            provider_layer_selections=[
                ProviderLayerSelection(
                    provider_id=provider_id,
                    layer_id=layer_id,
                    time=arguments.get("time") if isinstance(arguments.get("time"), str) else None,
                    style=arguments.get("style") if isinstance(arguments.get("style"), str) else None,
                    format=arguments.get("format") if isinstance(arguments.get("format"), str) else None,
                )
            ],
        )
        map_session = await self.search_orchestrator.execute(request)
        return self._map_result(
            capability_id=capability_id,
            arguments=arguments,
            map_session=map_session,
        )

    # -------------------------------------------------------------------------
    def list_geospatial_capabilities(
        self,
        filters: CapabilityCatalogFilter,
    ) -> dict[str, Any]:
        items = self._all_capabilities()
        query = str(filters.query or "").strip().casefold()
        category = str(filters.category or "").strip().casefold()
        geometry_type = str(filters.geometry_type or "").strip().casefold()
        if query:
            items = [
                item
                for item in items
                if query
                in " ".join(
                    [
                        str(item.get("id") or ""),
                        str(item.get("name") or ""),
                        str(item.get("description") or ""),
                    ]
                ).casefold()
            ]
        if category:
            items = [
                item
                for item in items
                if category
                in {
                    str(item.get("type") or "").casefold(),
                    str(item.get("capabilityKind") or "").casefold(),
                }
            ]
        if geometry_type:
            items = [
                item
                for item in items
                if geometry_type
                        == str(json_object(item.get("metadata")).get("geometry_type") or "").casefold()
            ]
        items = sorted(items, key=lambda item: str(item.get("id") or ""))
        offset = self._decode_cursor(filters.cursor)
        limit = max(1, min(filters.limit or CATALOG_PAGE_LIMIT, CATALOG_PAGE_LIMIT))
        page_items = items[offset : offset + limit]
        next_offset = offset + len(page_items)
        return {
            "items": [self._compact_descriptor(item) for item in page_items],
            "next_cursor": str(next_offset) if next_offset < len(items) else None,
            "limit": limit,
            "total": len(items),
        }

    # -------------------------------------------------------------------------
    def describe_geospatial_capability(self, capability_id: str) -> dict[str, Any]:
        capability = self.capability_registry.get_capability(capability_id)
        if capability is None:
            raise ValueError(f"Unknown geospatial capability '{capability_id}'.")
        return {
            "capability_id": capability_id,
            "manifest": capability,
            "argument_schema": self._argument_schema_for(capability),
        }

    # -------------------------------------------------------------------------
    async def execute_geospatial_capability(
        self,
        capability_id: str,
        arguments: dict[str, Any],
        *,
        context: AgentExecutionContext | None = None,
    ) -> GeospatialCapabilityExecutionResult:
        descriptor = self.describe_geospatial_capability(capability_id)
        validation_error = ToolRegistry._validate_arguments(  # pyright: ignore[reportPrivateUsage]
            descriptor["argument_schema"],
            arguments,
        )
        if validation_error is not None:
            return self._error_result(
                capability_id=capability_id,
                arguments=arguments,
                operation="invalid_arguments",
                code="invalid_arguments",
                message=validation_error,
            )

        manifest = descriptor["manifest"]
        parsed_request = self._parsed_request_from_context(context)
        if self.policy_engine is not None and parsed_request is not None:
            authorization = self.policy_engine.authorize_capability_execution(
                capability_id,
                arguments,
                parsed_request,
                context or AgentExecutionContext(),
            )
            if not authorization.allowed:
                return self._authorization_error_result(
                    capability_id=capability_id,
                    arguments=arguments,
                    authorization=authorization,
                )

        if self._is_basemap_capability(manifest):
            if self.search_orchestrator is not None:
                resolved_location = await self._resolve_location(arguments, context)
                if not (is_json_object(resolved_location) and resolved_location.get("error")):
                    if not isinstance(resolved_location, ResolvedLocation):
                        return cast(GeospatialCapabilityExecutionResult, resolved_location)
                    plan = self._build_map_execution_plan(
                        capability_id=capability_id,
                        manifest=manifest,
                        context=context,
                    )
                    request = self.request_builder.build_location_search_request(
                        plan,
                        resolved_location,
                        turn_contract=self._parsed_turn(context),
                        active_visualization=(
                            context.map_state.get("active_visualization")
                            if context is not None and is_json_object(context.map_state)
                            else None
                        ),
                    )
                    map_session = await self.search_orchestrator.execute(request)
                    return self._map_result(
                        capability_id=capability_id,
                        arguments=arguments,
                        map_session=map_session,
                    )
            return self._capability_selection_result(
                capability_id=capability_id,
                arguments=arguments,
                selection={"basemap_id": capability_id, "overlay_ids": []},
            )

        if self._supports_direct_execution(capability_id, manifest):
            direct_result = await self._execute_direct_result(
                capability_id=capability_id,
                arguments=arguments,
                context=context,
            )
            if direct_result.get("ok") is False:
                return direct_result
            return direct_result

        if self._supports_map_execution(capability_id, manifest):
            if self.search_orchestrator is None:
                return self._error_result(
                    capability_id=capability_id,
                    arguments=arguments,
                    operation="provider_error",
                    code="provider_error",
                    message="Search orchestrator is not configured for map execution.",
                )
            resolved_location = await self._resolve_location(arguments, context)
            if is_json_object(resolved_location) and resolved_location.get("error"):
                return cast(GeospatialCapabilityExecutionResult, resolved_location)
            if not isinstance(resolved_location, ResolvedLocation):
                return cast(GeospatialCapabilityExecutionResult, resolved_location)
            plan = self._build_map_execution_plan(capability_id=capability_id, manifest=manifest, context=context)
            request = self.request_builder.build_location_search_request(
                plan,
                resolved_location,
                turn_contract=self._parsed_turn(context),
                active_visualization=(
                    context.map_state.get("active_visualization")
                    if context is not None and is_json_object(context.map_state)
                    else None
                ),
            )
            map_session = await self.search_orchestrator.execute(request)
            return self._map_result(
                capability_id=capability_id,
                arguments=arguments,
                map_session=map_session,
            )

        return {
            "capability_id": capability_id,
            "arguments": arguments,
            "ok": True,
            "operation": "validated_only",
            "map_session": None,
            "direct_result": None,
            "capability_selection": None,
            "observations": [],
            "warnings": [],
            "error": None,
            "metadata": {"manifest": self._compact_descriptor(manifest)},
        }

    # -------------------------------------------------------------------------
    def _all_capabilities(self) -> list[dict[str, Any]]:
        snapshot = self.capability_registry.load_capabilities()
        return [
            *snapshot.basemaps,
            *snapshot.overlays,
            *snapshot.cameras,
            *snapshot.transit,
            *snapshot.tools,
        ]

    # -------------------------------------------------------------------------
    @staticmethod
    def _compact_descriptor(item: dict[str, Any]) -> dict[str, Any]:
        metadata = json_object(item.get("metadata"))
        return {
            "id": item.get("id"),
            "name": item.get("name"),
            "description": item.get("description"),
            "provider": item.get("provider"),
            "category": item.get("capabilityKind") or item.get("type"),
            "geometry_type": metadata.get("geometry_type"),
            "queryable": metadata.get("queryable"),
        }

    # -------------------------------------------------------------------------
    @staticmethod
    def _argument_schema_for(capability: dict[str, Any]) -> dict[str, Any]:
        metadata = json_object(capability.get("metadata"))
        schema = metadata.get("parameters_json_schema") or metadata.get("argument_schema")
        if is_json_object(schema):
            return schema
        return {"type": "object", "properties": {}}

    # -------------------------------------------------------------------------
    @staticmethod
    def _decode_cursor(cursor: str | None) -> int:
        if cursor is None:
            return 0
        try:
            return max(0, int(cursor))
        except ValueError:
            return 0

    # -------------------------------------------------------------------------
    @staticmethod
    def _is_basemap_capability(manifest: dict[str, Any]) -> bool:
        return str(manifest.get("capabilityKind") or manifest.get("type") or "").strip().lower() == "basemap"

    # -------------------------------------------------------------------------
    def _supports_direct_execution(self, capability_id: str, manifest: dict[str, Any]) -> bool:
        if self.tool_registry is None:
            return False
        return self.runtime_registry.supports_mode(capability_id, "direct_text") and self.tool_registry.get_handler(
            capability_id
        ) is not None

    # -------------------------------------------------------------------------
    def _supports_map_execution(self, capability_id: str, manifest: dict[str, Any]) -> bool:
        if self._is_basemap_capability(manifest):
            return False
        return self.runtime_registry.supports_mode(capability_id, "map")

    # -------------------------------------------------------------------------
    @staticmethod
    def _authorization_error_result(
        *,
        capability_id: str,
        arguments: dict[str, Any],
        authorization: ToolAuthorizationResult,
    ) -> GeospatialCapabilityExecutionResult:
        metadata = dict(authorization.metadata or {})
        code = str(metadata.get("code") or "unsupported_capability")
        operation_by_code = {
            "missing_credentials": "missing_credentials",
            "invalid_arguments": "invalid_arguments",
            "tool_rejected": "provider_error",
            "unsupported_capability": "unsupported_capability",
        }
        operation = operation_by_code.get(code, "unsupported_capability")
        warnings = [authorization.reason] if code == "missing_credentials" and authorization.reason else []
        return {
            "ok": False,
            "operation": operation,
            "capability_id": capability_id,
            "arguments": arguments,
            "map_session": None,
            "direct_result": None,
            "capability_selection": None,
            "observations": [],
            "warnings": warnings,
            "error": {
                "code": code,
                "message": authorization.reason or "Capability execution rejected.",
            },
            "metadata": metadata,
        }

    # -------------------------------------------------------------------------
    async def _execute_direct_result(
        self,
        *,
        capability_id: str,
        arguments: dict[str, Any],
        context: AgentExecutionContext | None,
    ) -> GeospatialCapabilityExecutionResult:
        if self.tool_registry is None:
            return self._error_result(
                capability_id=capability_id,
                arguments=arguments,
                operation="provider_error",
                code="provider_error",
                message="Tool registry is not configured for direct execution.",
            )
        resolved_location = await self._resolve_location(arguments, context)
        if is_json_object(resolved_location) and resolved_location.get("error"):
            return cast(GeospatialCapabilityExecutionResult, resolved_location)
        if not isinstance(resolved_location, ResolvedLocation):
            return cast(GeospatialCapabilityExecutionResult, resolved_location)
        plan = self._build_direct_execution_plan(capability_id=capability_id, context=context)
        direct_result = await self.tool_registry.execute(capability_id, plan, resolved_location)
        if is_json_object(direct_result) and direct_result.get("error"):
            return self._error_result(
                capability_id=capability_id,
                arguments=arguments,
                operation="provider_error",
                code="provider_error",
                message=str(direct_result["error"]),
            )
        return {
            "ok": True,
            "operation": "direct_result_created",
            "capability_id": capability_id,
            "arguments": arguments,
            "map_session": None,
            "direct_result": direct_result,
            "capability_selection": None,
            "observations": [],
            "warnings": [],
            "error": None,
            "metadata": {},
        }

    # -------------------------------------------------------------------------
    async def _resolve_location(
        self,
        arguments: dict[str, Any],
        context: AgentExecutionContext | None,
    ) -> ResolvedLocation | GeospatialCapabilityExecutionResult:
        argument_signals = self._build_argument_location_signals(arguments)
        parsed_request = self._parsed_request_from_context(context)
        parsed_signals = parsed_request.location_signals if parsed_request is not None else []
        memory_snapshot = context.map_state if context is not None else {}
        resolved = await self.location_resolver.resolve_location_signals(
            [*argument_signals, *parsed_signals],
            json_object(memory_snapshot),
        )
        if isinstance(resolved, ClarificationRequest):
            return self._error_result(
                capability_id="location_resolution",
                arguments=arguments,
                operation="invalid_arguments",
                code="missing_location",
                message=resolved.question,
            )
        return resolved

    # -------------------------------------------------------------------------
    def _build_map_execution_plan(
        self,
        *,
        capability_id: str,
        manifest: dict[str, Any],
        context: AgentExecutionContext | None,
    ) -> ExecutionPlan:
        parsed_request = self._parsed_request_from_context(context)
        action_id = (
            parsed_request.normalized_action.action_id
            if parsed_request is not None
            else str(manifest.get("id") or capability_id)
        )
        if self._is_basemap_capability(manifest):
            return ExecutionPlan(state="map_search", mode="map", action_id=action_id, basemap_id=capability_id)
        return ExecutionPlan(
            state="map_search",
            mode="map",
            action_id=action_id,
            basemap_id=None,
            overlay_ids=[capability_id],
        )

    # -------------------------------------------------------------------------
    def _build_direct_execution_plan(
        self,
        *,
        capability_id: str,
        context: AgentExecutionContext | None,
    ) -> ExecutionPlan:
        parsed_request = self._parsed_request_from_context(context)
        action_id = parsed_request.normalized_action.action_id if parsed_request is not None else capability_id
        temporal_mode = parsed_request.temporal_signal.mode if parsed_request is not None else None
        temporal_text = parsed_request.temporal_signal.raw_text if parsed_request is not None else None
        return ExecutionPlan(
            state="direct_tool",
            mode="direct_text",
            action_id=action_id,
            temporal_mode=None if temporal_mode == "none" else temporal_mode,
            temporal_text=temporal_text,
            tool_id=capability_id,
        )

    # -------------------------------------------------------------------------
    def _build_argument_location_signals(
        self, arguments: dict[str, Any]
    ) -> list[LocationSignal]:
        signals: list[LocationSignal] = []
        location_text = arguments.get("location") or arguments.get("location_text") or arguments.get("query")
        if isinstance(location_text, str) and location_text.strip():
            signals.append(
                LocationSignal(
                    signal_type="city",
                    raw_value=location_text.strip(),
                    normalized_value=location_text.strip(),
                    confidence=0.9,
                    source="model",
                )
            )
        latitude = arguments.get("latitude")
        longitude = arguments.get("longitude")
        if isinstance(latitude, int | float) and isinstance(longitude, int | float):
            signals.insert(
                0,
                LocationSignal(
                    signal_type="coordinates",
                    raw_value=f"{latitude},{longitude}",
                    normalized_value=f"{latitude},{longitude}",
                    latitude=float(latitude),
                    longitude=float(longitude),
                    confidence=1.0,
                    source="model",
                ),
            )
        return signals

    # -------------------------------------------------------------------------
    @staticmethod
    def _parsed_turn(context: AgentExecutionContext | None) -> TurnParseResult | None:
        if context is None:
            return None
        try:
            return TurnParseResult.model_validate(context.parsed_request)
        except Exception:
            return None

    # -------------------------------------------------------------------------
    @staticmethod
    def _parsed_request_from_context(context: AgentExecutionContext | None) -> TurnParseResult | None:
        if context is None or not is_json_object(context.parsed_request):
            return None
        try:
            return TurnParseResult.model_validate(context.parsed_request)
        except Exception:
            return None

    # -------------------------------------------------------------------------
    @staticmethod
    def _map_result(
        *,
        capability_id: str,
        arguments: dict[str, Any],
        map_session: MapSession,
    ) -> GeospatialCapabilityExecutionResult:
        return {
            "ok": True,
            "operation": "map_session_created",
            "capability_id": capability_id,
            "arguments": arguments,
            "map_session": map_session.model_dump(mode="json"),
            "direct_result": None,
            "capability_selection": None,
            "observations": [],
            "warnings": list(map_session.compliance_warnings),
            "error": None,
            "metadata": {},
        }

    # -------------------------------------------------------------------------
    @staticmethod
    def _capability_selection_result(
        *,
        capability_id: str,
        arguments: dict[str, Any],
        selection: dict[str, Any],
    ) -> GeospatialCapabilityExecutionResult:
        return {
            "ok": True,
            "operation": "capability_selection_created",
            "capability_id": capability_id,
            "arguments": arguments,
            "map_session": None,
            "direct_result": None,
            "capability_selection": selection,
            "observations": [],
            "warnings": [],
            "error": None,
            "metadata": {},
        }

    # -------------------------------------------------------------------------
    @staticmethod
    def _error_result(
        *,
        capability_id: str,
        arguments: dict[str, Any],
        operation: str,
        code: str,
        message: str,
    ) -> GeospatialCapabilityExecutionResult:
        return {
            "ok": False,
            "operation": operation,
            "capability_id": capability_id,
            "arguments": arguments,
            "map_session": None,
            "direct_result": None,
            "capability_selection": None,
            "observations": [],
            "warnings": [],
            "error": {"code": code, "message": message},
            "metadata": {},
        }
