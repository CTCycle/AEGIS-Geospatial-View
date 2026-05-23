from __future__ import annotations

from server.domain.agent.actions import AgentAction
from server.services.agent.tool_manifest import ToolManifestService


class _Registry:
    def list_overlays(self):
        return [
            {"id": "Rain Layer", "name": "Rain layer", "description": "rain precipitation", "metadata": {"queryable": True}},
            {"id": "traffic_flow", "name": "Traffic", "description": "traffic"},
            {"id": "air_quality", "name": "Air", "description": "air quality"},
            {"id": "fire_hotspots", "name": "Fire", "description": "fire"},
            {"id": "land_cover", "name": "Land", "description": "land"},
        ]

    def list_cameras(self):
        return []

    def list_transit(self):
        return []


def test_base_tools_are_present() -> None:
    names = {tool.name for tool in ToolManifestService(_Registry()).list_base_tools()}
    assert {"search_maps", "resolve_location", "load_map_overlay", "interrogate_visible_layers"}.issubset(names)


def test_overlay_tools_are_generated_with_safe_names() -> None:
    tools = ToolManifestService(_Registry()).list_overlay_tools()
    assert "overlay__rain_layer" in {tool.name for tool in tools}
    assert next(tool for tool in tools if tool.name == "overlay__rain_layer").source_capability_id == "Rain Layer"


def test_select_tools_respects_max_and_overlay_limit() -> None:
    service = ToolManifestService(_Registry())
    selected = service.select_tools(
        AgentAction.DATA_LAYER_QUERY,
        topic="rain",
        map_context={},
        visible_layer_ids=[],
        available_source_ids=[],
        max_tools=3,
    )
    assert len(selected) <= 3
    assert sum(1 for tool in selected if tool.name.startswith("overlay__")) <= 4


def test_external_source_tool_is_action_gated() -> None:
    service = ToolManifestService(_Registry())
    map_tools = service.select_tools(
        AgentAction.MAP_SEARCH,
        topic=None,
        map_context={},
        visible_layer_ids=[],
        available_source_ids=[],
    )
    fusion_tools = service.select_tools(
        AgentAction.MAP_EXTERNAL_SOURCE_COMBINATION,
        topic=None,
        map_context={},
        visible_layer_ids=[],
        available_source_ids=["source"],
    )
    assert "combine_map_data_with_external_sources" not in {tool.name for tool in map_tools}
    assert "combine_map_data_with_external_sources" in {tool.name for tool in fusion_tools}
