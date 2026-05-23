from __future__ import annotations

from server.domain.agent.actions import ACTION_CATALOG, AgentAction
from server.domain.agent.decision import AgentDecision, AgentToolCallPlanItem
from server.domain.extraction.models import TurnParseResult
from server.services.agent.parser_service import ParserService
from server.services.agent.tool_manifest import ToolManifestService

###############################################################################
class ActionRouter:
    def __init__(self, *, parser_service: ParserService, tool_manifest: ToolManifestService) -> None:
        self.parser_service = parser_service
        self.tool_manifest = tool_manifest

    # -------------------------------------------------------------------------
    def parse(self, user_message: str, memory_snapshot: dict, conversation_messages: list[dict]) -> TurnParseResult:
        return self.parser_service.parse_turn(user_message, memory_snapshot, conversation_messages)

    # -------------------------------------------------------------------------
    def decide(
        self,
        turn: TurnParseResult,
        *,
        map_context: dict | None = None,
        visible_layer_ids: list[str] | None = None,
        available_source_ids: list[str] | None = None,
        max_tools: int = 12,
    ) -> AgentDecision:
        action = self._coerce_action(turn.normalized_action.action_id, turn.task_class, turn.parser_confidence)
        definition = ACTION_CATALOG[action]
        tools = self.tool_manifest.select_tools(
            action,
            topic=" ".join([*turn.normalized_action.action_tags, *turn.normalized_action.requested_visualizations]),
            map_context=map_context,
            visible_layer_ids=visible_layer_ids or [],
            available_source_ids=available_source_ids or [],
            max_tools=max_tools,
        )
        return AgentDecision(
            action=definition.action,
            action_confidence=turn.parser_confidence,
            tool_names=[tool.name for tool in tools],
            tool_call_plan=[
                AgentToolCallPlanItem(tool_name=tool.name, reason=tool.description)
                for tool in tools
            ],
            requires_clarification=bool(turn.ambiguities and action != AgentAction.CHAT_RESPONSE),
            clarification_question="Which location should I use?" if "missing_location" in turn.ambiguities else None,
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def _coerce_action(action_id: str, task_class: str, confidence: float) -> AgentAction:
        if confidence < 0.25:
            return AgentAction.UNKNOWN
        try:
            return AgentAction(action_id)
        except ValueError:
            if task_class == "general_question":
                return AgentAction.CHAT_RESPONSE
            if task_class == "map_search":
                return AgentAction.MAP_SEARCH
            if task_class == "direct_query":
                return AgentAction.GEOSPATIAL_DATA_RETRIEVAL
            return AgentAction.UNKNOWN
