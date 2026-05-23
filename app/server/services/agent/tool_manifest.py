from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from server.domain.agent.actions import AgentAction
from server.domain.agent.tools import AgentToolDefinition, AgentToolName
from server.services.geospatial.capability_registry import CapabilityRegistry


def safe_tool_suffix(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]+", "_", value.strip()).strip("_").lower()


class ToolManifestService:
    def __init__(self, capability_registry: CapabilityRegistry) -> None:
        self.capability_registry = capability_registry

    def list_base_tools(self) -> list[AgentToolDefinition]:
        object_schema = {"type": "object", "properties": {}, "additionalProperties": True}
        return [
            AgentToolDefinition(
                name=AgentToolName.SEARCH_MAPS.value,
                description="Search map catalog and create a map search operation.",
                parameters_json_schema=object_schema,
                action_scope=[AgentAction.MAP_SEARCH, AgentAction.LOCATION_RENDER],
            ),
            AgentToolDefinition(
                name=AgentToolName.RESOLVE_LOCATION.value,
                description="Resolve a place, address, or coordinate mention.",
                parameters_json_schema=object_schema,
                action_scope=[AgentAction.MAP_SEARCH, AgentAction.LOCATION_RENDER],
            ),
            AgentToolDefinition(
                name=AgentToolName.RETRIEVE_GEOSPATIAL_DATA.value,
                description="Retrieve geospatial data for the active map context.",
                parameters_json_schema=object_schema,
                action_scope=[AgentAction.GEOSPATIAL_DATA_RETRIEVAL, AgentAction.DATA_LAYER_QUERY],
                requires_map_context=True,
            ),
            AgentToolDefinition(
                name=AgentToolName.QUERY_DATA_LAYER_API.value,
                description="Query a manifest-backed data layer API.",
                parameters_json_schema=object_schema,
                action_scope=[AgentAction.DATA_LAYER_QUERY, AgentAction.VISIBLE_LAYER_INTERROGATION],
                requires_map_context=True,
            ),
            AgentToolDefinition(
                name=AgentToolName.LOAD_MAP_OVERLAY.value,
                description="Load a map overlay by identifier.",
                parameters_json_schema=object_schema,
                action_scope=[AgentAction.OVERLAY_CONTROL, AgentAction.DATASET_DISPLAY],
                requires_map_context=True,
            ),
            AgentToolDefinition(
                name=AgentToolName.TOGGLE_MAP_OVERLAY.value,
                description="Toggle a map overlay visibility state.",
                parameters_json_schema=object_schema,
                action_scope=[AgentAction.OVERLAY_CONTROL],
                requires_map_context=True,
            ),
            AgentToolDefinition(
                name=AgentToolName.DISPLAY_DATASET_ON_MAP.value,
                description="Display a dataset on the map.",
                parameters_json_schema=object_schema,
                action_scope=[AgentAction.DATASET_DISPLAY],
                requires_map_context=True,
            ),
            AgentToolDefinition(
                name=AgentToolName.INTERROGATE_VISIBLE_LAYERS.value,
                description="Inspect or summarize visible map layers.",
                parameters_json_schema=object_schema,
                action_scope=[AgentAction.VISIBLE_LAYER_INTERROGATION],
                requires_map_context=True,
            ),
            AgentToolDefinition(
                name=AgentToolName.COMBINE_MAP_DATA_WITH_EXTERNAL_SOURCES.value,
                description="Combine visible map data with permitted external sources.",
                parameters_json_schema=object_schema,
                action_scope=[AgentAction.MAP_EXTERNAL_SOURCE_COMBINATION],
                requires_map_context=True,
            ),
        ]

    def list_overlay_tools(self) -> list[AgentToolDefinition]:
        tools: list[AgentToolDefinition] = []
        for capability in [
            *self.capability_registry.list_overlays(),
            *self.capability_registry.list_cameras(),
            *self.capability_registry.list_transit(),
        ]:
            capability_id = str(capability.get("id") or "").strip()
            if not capability_id:
                continue
            metadata = capability.get("metadata") if isinstance(capability.get("metadata"), dict) else {}
            queryable = bool(metadata.get("queryable") or capability.get("queryable"))
            scope = [AgentAction.OVERLAY_CONTROL, AgentAction.DATASET_DISPLAY]
            if queryable:
                scope.extend([AgentAction.DATA_LAYER_QUERY, AgentAction.VISIBLE_LAYER_INTERROGATION])
            tools.append(
                AgentToolDefinition(
                    name=f"overlay__{safe_tool_suffix(capability_id)}",
                    description=str(capability.get("description") or capability.get("name") or capability_id),
                    parameters_json_schema={
                        "type": "object",
                        "properties": {
                            "operation": {"type": "string"},
                            "visible": {"type": "boolean"},
                            "opacity": {"type": "number"},
                        },
                        "additionalProperties": True,
                    },
                    action_scope=scope,
                    requires_map_context=True,
                    source_manifest_id=capability_id,
                    source_capability_id=capability_id,
                )
            )
        return tools

    def list_all_tools(self) -> list[AgentToolDefinition]:
        return [*self.list_base_tools(), *self.list_overlay_tools()]

    def select_tools(
        self,
        action: AgentAction,
        *,
        topic: str | None,
        map_context: Mapping[str, Any] | None,
        visible_layer_ids: Sequence[str],
        available_source_ids: Sequence[str],
        max_tools: int = 12,
    ) -> list[AgentToolDefinition]:
        del available_source_ids
        selected: list[AgentToolDefinition] = []
        base = [tool for tool in self.list_base_tools() if action in tool.action_scope]
        needs_location = action in {AgentAction.MAP_SEARCH, AgentAction.LOCATION_RENDER}
        if needs_location and not (map_context or {}).get("viewport"):
            resolver = next((tool for tool in self.list_base_tools() if tool.name == AgentToolName.RESOLVE_LOCATION.value), None)
            if resolver is not None:
                selected.append(resolver)
        for tool in base:
            if action != AgentAction.MAP_EXTERNAL_SOURCE_COMBINATION and tool.name == AgentToolName.COMBINE_MAP_DATA_WITH_EXTERNAL_SOURCES.value:
                continue
            if tool.name not in {item.name for item in selected}:
                selected.append(tool)

        overlay_tools = [tool for tool in self.list_overlay_tools() if action in tool.action_scope]
        visible = {str(item) for item in visible_layer_ids}
        topic_tokens = {token for token in re.split(r"[^a-zA-Z0-9_]+", str(topic or "").lower()) if token}

        overlay_limit = max_tools if action in {AgentAction.OVERLAY_CONTROL, AgentAction.DATASET_DISPLAY} else 4
        for tool in sorted(
            overlay_tools,
            key=lambda item: self._tool_selection_score(item, visible, topic_tokens),
            reverse=True,
        )[:overlay_limit]:
            if len(selected) >= max_tools:
                break
            selected.append(tool)
        return selected[:max_tools]

    @staticmethod
    def _tool_selection_score(
        tool: AgentToolDefinition,
        visible_layer_ids: set[str],
        topic_tokens: set[str],
    ) -> tuple[int, str]:
        value = f"{tool.name} {tool.description} {tool.source_capability_id or ''}".lower()
        visible_score = 20 if (tool.source_capability_id or "") in visible_layer_ids else 0
        topic_score = sum(1 for token in topic_tokens if token and token in value)
        return (visible_score + topic_score, tool.name)
