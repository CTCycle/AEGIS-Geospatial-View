from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from server.domain.agent.tools import AgentToolCall, AgentToolResult, AgentToolName
from server.services.agent.tool_manifest import safe_tool_suffix
from server.services.geospatial.capability_registry import CapabilityRegistry


class AgentExecutionContext(BaseModel):
    model_config = ConfigDict(extra="allow")

    map_context: dict[str, Any] = Field(default_factory=dict)
    visible_layer_ids: list[str] = Field(default_factory=list)
    available_source_ids: list[str] = Field(default_factory=list)


class AgentToolExecutor:
    def __init__(self, *, capability_registry: CapabilityRegistry | None = None) -> None:
        self.capability_registry = capability_registry or CapabilityRegistry()

    async def execute(self, call: AgentToolCall, context: AgentExecutionContext) -> AgentToolResult:
        if call.name.startswith("overlay__"):
            return self._execute_overlay(call, context)
        handlers = {
            AgentToolName.SEARCH_MAPS.value: self._search_maps,
            AgentToolName.RESOLVE_LOCATION.value: self._resolve_location,
            AgentToolName.RETRIEVE_GEOSPATIAL_DATA.value: self._retrieve_geospatial_data,
            AgentToolName.QUERY_DATA_LAYER_API.value: self._query_data_layer_api,
            AgentToolName.LOAD_MAP_OVERLAY.value: self._load_map_overlay,
            AgentToolName.TOGGLE_MAP_OVERLAY.value: self._toggle_map_overlay,
            AgentToolName.DISPLAY_DATASET_ON_MAP.value: self._display_dataset_on_map,
            AgentToolName.INTERROGATE_VISIBLE_LAYERS.value: self._interrogate_visible_layers,
            AgentToolName.COMBINE_MAP_DATA_WITH_EXTERNAL_SOURCES.value: self._combine_map_data,
        }
        handler = handlers.get(call.name)
        if handler is None:
            return AgentToolResult(tool_call_id=call.id, name=call.name, error="Unknown tool name.")
        return AgentToolResult(tool_call_id=call.id, name=call.name, result=handler(call.arguments, context))

    def _capability_payload(self, capability_id: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        capability = self.capability_registry.get_capability(capability_id) or {}
        return {
            "overlay_id": capability_id,
            "layer_id": capability_id,
            "dataset_id": capability_id,
            "visibility": bool(arguments.get("visible", True)),
            "opacity": float(arguments.get("opacity", capability.get("default_opacity", 0.75) or 0.75)),
            "legend": capability.get("legend") or capability.get("name"),
            "source_attribution": capability.get("attribution") or capability.get("provider"),
        }

    def _execute_overlay(self, call: AgentToolCall, context: AgentExecutionContext) -> AgentToolResult:
        suffix = call.name.removeprefix("overlay__")
        candidates = [
            *self.capability_registry.list_overlays(),
            *self.capability_registry.list_cameras(),
            *self.capability_registry.list_transit(),
        ]
        capability_id = next(
            (str(item.get("id")) for item in candidates if safe_tool_suffix(str(item.get("id") or "")) == suffix),
            None,
        )
        if capability_id is None:
            return AgentToolResult(tool_call_id=call.id, name=call.name, error="Overlay capability not found.")
        return AgentToolResult(
            tool_call_id=call.id,
            name=call.name,
            result={"type": "load_overlay", **self._capability_payload(capability_id, call.arguments), "map_context": context.map_context},
        )

    def _search_maps(self, arguments: Mapping[str, Any], context: AgentExecutionContext) -> dict[str, Any]:
        return {"type": "set_viewport", "viewport": arguments.get("viewport") or context.map_context.get("viewport"), "center": arguments.get("center"), "bbox": arguments.get("bbox"), "zoom": arguments.get("zoom")}

    def _resolve_location(self, arguments: Mapping[str, Any], context: AgentExecutionContext) -> dict[str, Any]:
        return {"type": "set_viewport", "center": arguments.get("center"), "viewport": arguments.get("viewport") or context.map_context.get("viewport"), "bbox": arguments.get("bbox"), "zoom": arguments.get("zoom", 11)}

    def _retrieve_geospatial_data(self, arguments: Mapping[str, Any], context: AgentExecutionContext) -> dict[str, Any]:
        return {"type": "data_retrieval", "bbox": arguments.get("bbox") or context.map_context.get("bbox"), "source_attribution": arguments.get("source_attribution")}

    def _query_data_layer_api(self, arguments: Mapping[str, Any], context: AgentExecutionContext) -> dict[str, Any]:
        return {"type": "show_layer_summary", "layer_id": arguments.get("layer_id"), "bbox": arguments.get("bbox") or context.map_context.get("bbox")}

    def _load_map_overlay(self, arguments: Mapping[str, Any], context: AgentExecutionContext) -> dict[str, Any]:
        return {"type": "load_overlay", **self._capability_payload(str(arguments.get("overlay_id") or arguments.get("layer_id") or ""), arguments), "map_context": context.map_context}

    def _toggle_map_overlay(self, arguments: Mapping[str, Any], context: AgentExecutionContext) -> dict[str, Any]:
        return {"type": "toggle_overlay", **self._capability_payload(str(arguments.get("overlay_id") or arguments.get("layer_id") or ""), arguments), "map_context": context.map_context}

    def _display_dataset_on_map(self, arguments: Mapping[str, Any], context: AgentExecutionContext) -> dict[str, Any]:
        return {"type": "display_dataset", "dataset_id": arguments.get("dataset_id") or arguments.get("layer_id"), "bbox": arguments.get("bbox") or context.map_context.get("bbox"), "source_attribution": arguments.get("source_attribution")}

    def _interrogate_visible_layers(self, arguments: Mapping[str, Any], context: AgentExecutionContext) -> dict[str, Any]:
        return {"type": "show_layer_summary", "layer_id": arguments.get("layer_id"), "visible_layer_ids": context.visible_layer_ids, "source_attribution": arguments.get("source_attribution")}

    def _combine_map_data(self, arguments: Mapping[str, Any], context: AgentExecutionContext) -> dict[str, Any]:
        return {"type": "show_layer_summary", "visible_layer_ids": context.visible_layer_ids, "external_sources": arguments.get("external_sources", []), "source_attribution": arguments.get("source_attribution")}
