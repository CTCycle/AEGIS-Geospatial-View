from __future__ import annotations

from server.domain.agent.actions import AgentAction
from server.domain.agent.tools import AgentToolDefinition
from server.services.agent.tool_manifest import ToolManifestService


class OverlayResolutionAgent:
    def __init__(self, tool_manifest: ToolManifestService) -> None:
        self.tool_manifest = tool_manifest

    def select_overlay_tools(self, *, action: AgentAction, topic: str | None, visible_layer_ids: list[str]) -> list[AgentToolDefinition]:
        return [
            tool
            for tool in self.tool_manifest.select_tools(
                action,
                topic=topic,
                map_context={},
                visible_layer_ids=visible_layer_ids,
                available_source_ids=[],
            )
            if tool.name.startswith("overlay__")
        ]
