from __future__ import annotations

from server.domain.agent.actions import AgentAction
from server.domain.agent.tools import AgentToolDefinition
from server.services.agent.tool_manifest import ToolManifestService


class MapDataFusionAgent:
    def __init__(self, tool_manifest: ToolManifestService) -> None:
        self.tool_manifest = tool_manifest

    def select_tools(self, *, visible_layer_ids: list[str], available_source_ids: list[str]) -> list[AgentToolDefinition]:
        return self.tool_manifest.select_tools(
            AgentAction.MAP_EXTERNAL_SOURCE_COMBINATION,
            topic=None,
            map_context={},
            visible_layer_ids=visible_layer_ids,
            available_source_ids=available_source_ids,
        )
