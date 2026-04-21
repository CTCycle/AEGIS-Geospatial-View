from __future__ import annotations

from typing import Any

from AEGIS.server.domain.chat import ChatTurnRequest, ChatTurnResponse
from AEGIS.server.repositories.chat_history import ChatHistoryRepository
from AEGIS.server.services.agent.location_memory import LocationMemoryService
from AEGIS.server.services.agent.parser_service import ParserService
from AEGIS.server.services.agent.policy_engine import PolicyEngine
from AEGIS.server.services.agent.tool_registry import ToolRegistry
from AEGIS.server.services.search.orchestrator import LocationSearchOrchestrator
from AEGIS.server.services.search.request_builder import RequestBuilder


class AgentOrchestrator:
    def __init__(
        self,
        *,
        search_orchestrator: LocationSearchOrchestrator,
        parser_service: ParserService,
        location_memory_service: LocationMemoryService,
        policy_engine: PolicyEngine,
        tool_registry: ToolRegistry,
        request_builder: RequestBuilder,
        history_repo: ChatHistoryRepository | None = None,
    ) -> None:
        self.search_orchestrator = search_orchestrator
        self.parser_service = parser_service
        self.location_memory_service = location_memory_service
        self.policy_engine = policy_engine
        self.tool_registry = tool_registry
        self.request_builder = request_builder
        self.history_repo = history_repo or ChatHistoryRepository()

    async def run_turn(self, payload: ChatTurnRequest) -> ChatTurnResponse:
        session = self.history_repo.upsert_session(payload.session_id, title=payload.title)
        self.history_repo.append_message(session_id=session.id, role="user", content=payload.message)

        recent_messages = self.history_repo.list_recent_messages(session.id, limit=12)
        latest_contract = self.history_repo.get_latest_turn_contract(session.id)
        latest_memory = self.history_repo.get_latest_memory_snapshot(session.id)

        turn_contract = self.parser_service.parse_turn(
            user_message=payload.message,
            memory_snapshot=latest_memory,
            conversation_messages=recent_messages,
        )

        decision = await self.policy_engine.decide(
            turn=turn_contract,
            memory_snapshot=latest_memory,
            runtime_registry=self.tool_registry.runtime_registry.build_snapshot(),
            capability_registry=self.search_orchestrator.capability_registry,
        )

        tool_payload: dict[str, Any] | None = None
        map_session = None
        assistant_message = "I need a clarification before I continue."
        memory_snapshot = latest_memory

        if decision.plan.state == "direct_tool" and decision.resolved_location is not None:
            tool_id = decision.plan.tool_id or "location_to_coordinates"
            tool_payload = await self.tool_registry.execute(tool_id, decision.plan, decision.resolved_location)
            assistant_message = self._compose_assistant_message(decision, tool_payload, None)
            memory_snapshot = self.location_memory_service.update_memory_snapshot(
                latest_memory,
                decision.resolved_location,
                turn_contract.normalized_intent,
            )
        elif decision.plan.state == "map_search" and decision.resolved_location is not None:
            request = self.request_builder.build_location_search_request(
                decision.plan,
                decision.resolved_location,
            )
            map_session = await self.search_orchestrator.execute(request)
            assistant_message = self._compose_assistant_message(decision, None, map_session.model_dump(mode="json"))
            memory_snapshot = self.location_memory_service.update_memory_snapshot(
                latest_memory,
                decision.resolved_location,
                turn_contract.normalized_intent,
            )
        elif decision.clarification is not None:
            assistant_message = decision.clarification.question
        elif decision.plan.state == "reject":
            assistant_message = "I cannot execute this request with the current policy constraints."

        self.history_repo.append_message(
            session_id=session.id,
            role="assistant",
            content=assistant_message,
            structured_payload={
                "turn_contract": turn_contract.model_dump(mode="json"),
                "decision": decision.model_dump(mode="json"),
                "memory_snapshot": memory_snapshot,
                "previous_turn_contract": latest_contract,
            },
            tool_payload=tool_payload,
            map_session=map_session.model_dump(mode="json") if map_session is not None else None,
        )

        return ChatTurnResponse(
            session_id=session.id,
            assistant_message=assistant_message,
            turn_contract=turn_contract,
            decision=decision,
            tool_payload=tool_payload,
            map_session=map_session,
            memory_snapshot=memory_snapshot,
        )

    def _compose_assistant_message(
        self,
        decision,
        tool_payload: dict[str, Any] | None,
        map_payload: dict[str, Any] | None,
    ) -> str:
        if decision.plan.state == "direct_tool":
            return f"Executed direct tool '{decision.plan.tool_id}'."
        if decision.plan.state == "map_search" and isinstance(map_payload, dict):
            return (
                f"Prepared map session with basemap '{map_payload.get('basemap_id')}' "
                f"and overlays {map_payload.get('overlay_ids')}."
            )
        if isinstance(tool_payload, dict) and tool_payload.get("error"):
            return str(tool_payload["error"])
        return "Done."
