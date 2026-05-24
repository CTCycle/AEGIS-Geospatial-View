from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import pytest

from server.domain.chat import ChatTurnRequest
from server.domain.extraction.models import (
    ConversationContextSnapshot,
    NormalizedAction,
    TurnParseResult,
)
from server.services.agent.native_tool_loop import AgentToolLoopResult
from server.services.agent.orchestrator import AgentOrchestrator
from server.services.agent.policy_engine import AgentPolicyConstraints
from server.services.agent.tool_registry import ToolRegistry
from server.services.llm.types import LLMToolCall, LLMToolDefinition, LLMToolResult


@dataclass
class _Session:
    id: int = 7


@dataclass
class _Settings:
    agent_model_provider: str = "openai"
    agent_model_name: str = "gpt-4.1"


class _HistoryRepo:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    def upsert_session(self, session_id, title=None):  # noqa: ANN001
        return _Session(id=session_id or 7)

    def append_message(self, **kwargs: Any) -> None:
        self.messages.append(kwargs)

    def list_recent_messages(self, session_id: int, limit: int) -> list[dict[str, Any]]:
        return []

    def get_latest_turn_contract(self, session_id: int):
        return None

    def get_latest_memory_snapshot(self, session_id: int) -> dict[str, Any]:
        return {}


class _Parser:
    last_context_usage = None

    def parse_turn(self, user_message: str, memory_snapshot: dict, conversation_messages: list[dict]) -> TurnParseResult:
        return TurnParseResult(
            user_text=user_message,
            conversation_context=ConversationContextSnapshot(
                recent_messages=[],
                memory_snapshot=memory_snapshot,
            ),
            task_class="map_search",
            location_signals=[],
            normalized_action=NormalizedAction(
                action_id="map_search",
                action_label="Map Search",
                task_tags=["map"],
                action_tags=["catalog"],
                requires_location=False,
            ),
            parser_confidence=0.9,
        )


class _Policy:
    decide_called = False

    def _validate_task_class(self, turn):
        return None

    def _enforce_location_policy(self, turn):
        return None

    def _enforce_safety_policy(self, turn):
        return None

    def build_agent_constraints(self, parsed_request, map_state):
        return AgentPolicyConstraints(
            requires_location=False,
            allowed_tool_names=["list_geospatial_capabilities"],
        )

    async def decide(self, *args, **kwargs):
        self.decide_called = True
        raise AssertionError("legacy policy selection should not be called")


class _Catalog:
    def register_with(self, registry: ToolRegistry) -> None:
        registry.register_native_tool(
            LLMToolDefinition(
                name="list_geospatial_capabilities",
                description="List",
                parameters_json_schema={"type": "object", "properties": {}},
            ),
            self._handler,
        )

    async def _handler(self, arguments: dict[str, Any], context: Any) -> dict[str, Any]:
        return {"items": []}


class _NativeLoop:
    def __init__(self) -> None:
        self.requests: list[Any] = []

    async def run(self, request):
        self.requests.append(request)
        return AgentToolLoopResult(
            final_text="Catalog checked.",
            tool_calls=[
                LLMToolCall(
                    id="1",
                    name="list_geospatial_capabilities",
                    arguments={},
                )
            ],
            tool_results=[
                LLMToolResult(
                    tool_call_id="1",
                    name="list_geospatial_capabilities",
                    content={"ok": True, "data": {"items": []}},
                )
            ],
            iterations=1,
            stopped_reason="final",
        )


class _SettingsRepo:
    def get_or_create(self) -> _Settings:
        return _Settings()


def test_orchestrator_uses_native_tool_loop_for_agent_path() -> None:
    async def _run() -> None:
        policy = _Policy()
        native_loop = _NativeLoop()
        history = _HistoryRepo()
        orchestrator = AgentOrchestrator(
            search_orchestrator=object(),  # type: ignore[arg-type]
            parser_service=_Parser(),  # type: ignore[arg-type]
            location_memory_service=object(),  # type: ignore[arg-type]
            policy_engine=policy,  # type: ignore[arg-type]
            tool_registry=ToolRegistry(),
            request_builder=object(),  # type: ignore[arg-type]
            native_tool_loop=native_loop,  # type: ignore[arg-type]
            agent_tool_catalog_service=_Catalog(),  # type: ignore[arg-type]
            settings_repo=_SettingsRepo(),  # type: ignore[arg-type]
            history_repo=history,  # type: ignore[arg-type]
        )

        response = await orchestrator.run_turn(ChatTurnRequest(message="show catalog"))

        assert response.assistant_message == "Catalog checked."
        assert response.decision.plan.state == "direct_response"
        assert response.tool_payload is not None
        assert response.tool_payload["tool_calls"][0]["name"] == "list_geospatial_capabilities"
        assert native_loop.requests[0].tools[0].name == "list_geospatial_capabilities"
        assert policy.decide_called is False

    asyncio.run(_run())

