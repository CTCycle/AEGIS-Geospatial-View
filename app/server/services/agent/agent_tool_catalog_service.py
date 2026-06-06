from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypedDict

from server.domain.agent.decision import ExecutionPlan
from server.domain.extraction.models import TurnParseResult
from server.domain.geographics import MapSession
from server.services.agent.location_resolver import LocationResolver
from server.services.agent.native_tool_loop import AgentExecutionContext
from server.services.agent.policy_engine import PolicyEngine
from server.services.agent.tool_registry import ToolRegistry
from server.services.geospatial.capability_registry import CapabilityRegistry
from server.services.geospatial.manifest_loader import GeospatialManifestLoader
from server.services.geospatial.runtime_registry import RuntimeRegistry
from server.services.llm.types import LLMToolDefinition
from server.services.search.orchestrator import LocationSearchOrchestrator
from server.services.search.request_builder import RequestBuilder

CATALOG_PAGE_LIMIT = 50


@dataclass(frozen=True)
class CapabilityCatalogFilter:
    query: str | None = None
    category: str | None = None
    geometry_type: str | None = None
    bbox: list[float] | None = None
    limit: int = CATALOG_PAGE_LIMIT
    cursor: str | None = None


class GeospatialCapabilityExecutionResult(TypedDict, total=False):
    ok: bool
    operation: str
    capability_id: str
    arguments: dict[str, Any]
    map_session: dict[str, Any] | None
    direct_result: dict[str, Any] | None
    capability_selection: dict[str, Any] | None
    observations: list[dict[str, Any]]
    warnings: list[str]
    error: dict[str, str] | None
    metadata: dict[str, Any]


class AgentToolCatalogService:
    def __init__(
        self,
        *,
        capability_registry: CapabilityRegistry | None = None,
        manifest_loader: GeospatialManifestLoader | None = None,
        runtime_registry: RuntimeRegistry | None = None,
        search_orchestrator: LocationSearchOrchestrator | None = None,
        request_builder: RequestBuilder | None = None,
        location_resolver: LocationResolver | None = None,
        tool_registry: ToolRegistry | None = None,
        policy_engine: PolicyEngine | None = None,
    ) -> None:
        self.capability_registry = capability_registry or CapabilityRegistry()
        self.manifest_loader = manifest_loader or GeospatialManifestLoader()
        self.runtime_registry = runtime_registry or RuntimeRegistry()
        self.search_orchestrator = search_orchestrator
        self.request_builder = request_builder or RequestBuilder()
        self.location_resolver = location_resolver or LocationResolver()
        self.tool_registry = tool_registry
        self.policy_engine = policy_engine

    def build_native_tools(
        self,
        context: AgentExecutionContext | None = None,
    ) -> list[LLMToolDefinition]:
        _ = context
        return [
            LLMToolDefinition(
                name="list_geospatial_capabilities",
                description="List available geospatial capabilities with deterministic pagination and filters.",
                parameters_json_schema={
                    "type": "object",
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
                    "properties": {"capability_id": {"type": "string"}},
                    "required": ["capability_id"],
                },
            ),
            LLMToolDefinition(
                name="execute_geospatial_capability",
                description="Execute a geospatial capability by stable manifest capability_id after schema validation.",
                parameters_json_schema={
                    "type": "object",
                    "properties": {
                        "capability_id": {"type": "string"},
                        "arguments": {"type": "object"},
                    },
                    "required": ["capability_id", "arguments"],
                },
            ),
        ]

    def register_with(self, registry: ToolRegistry) -> None:
        for definition in self.build_native_tools():
            if definition.name == "list_geospatial_capabilities":
                registry.register_native_tool(definition, self._list_tool_handler)
            elif definition.name == "describe_geospatial_capability":
                registry.register_native_tool(definition, self._describe_tool_handler)
            elif definition.name == "execute_geospatial_capability":
                registry.register_native_tool(definition, self._execute_tool_handler)

    async def _list_tool_handler(
        self,
        arguments: dict[str, Any],
        context: AgentExecutionContext,
    ) -> dict[str, Any]:
        _ = context
        return self.list_geospatial_capabilities(CapabilityCatalogFilter(**arguments))

    async def _describe_tool_handler(
        self,
        arguments: dict[str, Any],
        context: AgentExecutionContext,
    ) -> dict[str, Any]:
        _ = context
        return self.describe_geospatial_capability(str(arguments["capability_id"]))

    async def _execute_tool_handler(
        self,
        arguments: dict[str, Any],
        context: AgentExecutionContext,
    ) -> dict[str, Any]:
        return await self.execute_geospatial_capability(
            str(arguments["capability_id"]),
            dict(arguments.get("arguments") or {}),
            context=context,
        )

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
                == str((item.get("metadata") or {}).get("geometry_type") or "").casefold()
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

    def describe_geospatial_capability(self, capability_id: str) -> dict[str, Any]:
        capability = self.capability_registry.get_capability(capability_id)
        if capability is None:
            raise ValueError(f"Unknown geospatial capability '{capability_id}'.")
        return {
            "capability_id": capability_id,
            "manifest": capability,
            "argument_schema": self._argument_schema_for(capability),
        }

    async def execute_geospatial_capability(
        self,
        capability_id: str,
        arguments: dict[str, Any],
        *,
        context: AgentExecutionContext | None = None,
    ) -> GeospatialCapabilityExecutionResult:
        descriptor = self.describe_geospatial_capability(capability_id)
        validation_error = ToolRegistry._validate_arguments(
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
            if isinstance(resolved_location, dict) and resolved_location.get("error"):
                return resolved_location
            plan = self._build_map_execution_plan(capability_id=capability_id, manifest=manifest, context=context)
            request = self.request_builder.build_location_search_request(plan, resolved_location)
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

    def _all_capabilities(self) -> list[dict[str, Any]]:
        snapshot = self.capability_registry.load_capabilities()
        return [
            *snapshot.basemaps,
            *snapshot.overlays,
            *snapshot.cameras,
            *snapshot.transit,
            *snapshot.tools,
        ]

    @staticmethod
    def _compact_descriptor(item: dict[str, Any]) -> dict[str, Any]:
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        return {
            "id": item.get("id"),
            "name": item.get("name"),
            "description": item.get("description"),
            "provider": item.get("provider"),
            "category": item.get("capabilityKind") or item.get("type"),
            "geometry_type": metadata.get("geometry_type"),
            "queryable": metadata.get("queryable"),
        }

    @staticmethod
    def _argument_schema_for(capability: dict[str, Any]) -> dict[str, Any]:
        metadata = capability.get("metadata") if isinstance(capability.get("metadata"), dict) else {}
        schema = metadata.get("parameters_json_schema") or metadata.get("argument_schema")
        if isinstance(schema, dict):
            return schema
        return {"type": "object", "properties": {}}

    @staticmethod
    def _decode_cursor(cursor: str | None) -> int:
        if cursor is None:
            return 0
        try:
            return max(0, int(cursor))
        except ValueError:
            return 0

    @staticmethod
    def _is_basemap_capability(manifest: dict[str, Any]) -> bool:
        return str(manifest.get("capabilityKind") or manifest.get("type") or "").strip().lower() == "basemap"

    def _supports_direct_execution(self, capability_id: str, manifest: dict[str, Any]) -> bool:
        if self.tool_registry is None:
            return False
        return self.runtime_registry.supports_mode(capability_id, "direct_text") and self.tool_registry.get_handler(
            capability_id
        ) is not None

    def _supports_map_execution(self, capability_id: str, manifest: dict[str, Any]) -> bool:
        if self._is_basemap_capability(manifest):
            return False
        return self.runtime_registry.supports_mode(capability_id, "map")

    @staticmethod
    def _authorization_error_result(
        *,
        capability_id: str,
        arguments: dict[str, Any],
        authorization,
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
        if isinstance(resolved_location, dict) and resolved_location.get("error"):
            return resolved_location
        plan = self._build_direct_execution_plan(capability_id=capability_id, context=context)
        direct_result = await self.tool_registry.execute(capability_id, plan, resolved_location)
        if isinstance(direct_result, dict) and direct_result.get("error"):
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

    async def _resolve_location(
        self,
        arguments: dict[str, Any],
        context: AgentExecutionContext | None,
    ):
        argument_signals = self._build_argument_location_signals(arguments)
        parsed_request = self._parsed_request_from_context(context)
        parsed_signals = parsed_request.location_signals if parsed_request is not None else []
        memory_snapshot = context.map_state if context is not None else {}
        resolved = await self.location_resolver.resolve_location_signals(
            [*argument_signals, *parsed_signals],
            memory_snapshot if isinstance(memory_snapshot, dict) else {},
        )
        if hasattr(resolved, "missing_fields"):
            return self._error_result(
                capability_id="location_resolution",
                arguments=arguments,
                operation="invalid_arguments",
                code="missing_location",
                message=str(resolved.question),
            )
        return resolved

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

    def _build_argument_location_signals(self, arguments: dict[str, Any]):
        from server.domain.extraction.models import LocationSignal

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

    @staticmethod
    def _parsed_request_from_context(context: AgentExecutionContext | None) -> TurnParseResult | None:
        if context is None or not isinstance(context.parsed_request, dict):
            return None
        try:
            return TurnParseResult.model_validate(context.parsed_request)
        except Exception:
            return None

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

