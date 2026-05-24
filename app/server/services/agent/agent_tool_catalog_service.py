from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from server.services.agent.native_tool_loop import AgentExecutionContext
from server.services.agent.tool_registry import ToolRegistry
from server.services.geospatial.capability_registry import CapabilityRegistry
from server.services.geospatial.manifest_loader import GeospatialManifestLoader
from server.services.geospatial.runtime_registry import RuntimeRegistry
from server.services.llm.types import LLMToolDefinition

CATALOG_PAGE_LIMIT = 50


@dataclass(frozen=True)
class CapabilityCatalogFilter:
    query: str | None = None
    category: str | None = None
    geometry_type: str | None = None
    bbox: list[float] | None = None
    limit: int = CATALOG_PAGE_LIMIT
    cursor: str | None = None


class AgentToolCatalogService:
    def __init__(
        self,
        *,
        capability_registry: CapabilityRegistry | None = None,
        manifest_loader: GeospatialManifestLoader | None = None,
        runtime_registry: RuntimeRegistry | None = None,
    ) -> None:
        self.capability_registry = capability_registry or CapabilityRegistry()
        self.manifest_loader = manifest_loader or GeospatialManifestLoader()
        self.runtime_registry = runtime_registry or RuntimeRegistry()

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
        _ = context
        return self.execute_geospatial_capability(
            str(arguments["capability_id"]),
            dict(arguments.get("arguments") or {}),
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

    def execute_geospatial_capability(
        self,
        capability_id: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        descriptor = self.describe_geospatial_capability(capability_id)
        validation_error = ToolRegistry._validate_arguments(
            descriptor["argument_schema"],
            arguments,
        )
        if validation_error is not None:
            raise ValueError(validation_error)
        return {
            "capability_id": capability_id,
            "arguments": arguments,
            "manifest": self._compact_descriptor(descriptor["manifest"]),
            "status": "validated",
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

