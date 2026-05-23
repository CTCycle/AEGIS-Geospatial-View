from __future__ import annotations

import asyncio

from server.domain.extraction.models import ConversationContextSnapshot, NormalizedAction, TurnParseResult
from server.services.agent.action_router import ActionRouter
from server.services.agent.agent_pipeline import AgentPipeline, AgentRequest
from server.services.agent.parser_service import ParserService
from server.services.agent.tool_executor import AgentToolExecutor
from server.services.agent.tool_manifest import ToolManifestService
from server.services.llm.types import LLMResult, LLMToolCall


class _Parser(ParserService):
    def __init__(self, action_id: str) -> None:
        self.action_id = action_id

    def parse_turn(self, user_message: str, memory_snapshot: dict, conversation_messages: list[dict]) -> TurnParseResult:
        return TurnParseResult(
            user_text=user_message,
            conversation_context=ConversationContextSnapshot(),
            task_class="general_question" if self.action_id == "chat_response" else "map_search",
            location_signals=[],
            normalized_action=NormalizedAction(
                action_id=self.action_id,
                action_label=self.action_id,
                task_tags=[],
                action_tags=[],
                requires_location=False,
            ),
            parser_confidence=0.9,
        )


class _Registry:
    def get_capability(self, capability_id: str):
        return {"id": capability_id, "name": capability_id, "provider": "test"}

    def list_overlays(self):
        return [{"id": "rain_layer", "name": "Rain", "description": "rain", "metadata": {"queryable": True}}]

    def list_cameras(self):
        return []

    def list_transit(self):
        return []


class _Provider:
    def chat(self, request, *, tools=None, tool_choice="auto", response_json_schema=None):
        return LLMResult(content="", tool_calls=[LLMToolCall(id="1", name="resolve_location", arguments={"zoom": 10})])


def test_pipeline_executes_provider_tool_calls() -> None:
    async def _run() -> None:
        registry = _Registry()
        manifest = ToolManifestService(registry)
        pipeline = AgentPipeline(
            action_router=ActionRouter(parser_service=_Parser("map_search"), tool_manifest=manifest),
            tool_manifest=manifest,
            tool_executor=AgentToolExecutor(capability_registry=registry),
            llm_provider=_Provider(),
        )
        response = await pipeline.run(AgentRequest(message="show Rome"))
        assert response.tool_calls
        assert response.map_operations
        assert "resolve_location" in response.tools_selected

    asyncio.run(_run())


def test_chat_action_does_not_expose_overlay_tools() -> None:
    async def _run() -> None:
        registry = _Registry()
        manifest = ToolManifestService(registry)
        pipeline = AgentPipeline(
            action_router=ActionRouter(parser_service=_Parser("chat_response"), tool_manifest=manifest),
            tool_manifest=manifest,
            tool_executor=AgentToolExecutor(capability_registry=registry),
            llm_provider=_Provider(),
        )
        response = await pipeline.run(AgentRequest(message="hello"))
        assert not any(name.startswith("overlay__") for name in response.tools_selected)
        assert response.tool_calls == []

    asyncio.run(_run())
