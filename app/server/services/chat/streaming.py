from __future__ import annotations

from collections.abc import AsyncIterator
from http import HTTPStatus
from typing import Any

from server.domain.chat import ChatStreamEvent, ChatTurnRequest, ChatTurnResponse
from server.services.agent.orchestrator import AgentOrchestrator
from server.services.llm.errors import LLMConfigurationError

###############################################################################
class ChatStreamingService:
    def __init__(self, agent_orchestrator: AgentOrchestrator) -> None:
        self.agent_orchestrator = agent_orchestrator

    # -------------------------------------------------------------------------
    async def stream_turn(self, payload: ChatTurnRequest) -> AsyncIterator[ChatStreamEvent]:
        request_id = payload.request_id or ""
        yield ChatStreamEvent(
            event="status",
            data={"message": "received", "request_id": request_id},
        )
        try:
            result = await self.agent_orchestrator.run_turn(payload)
            for token in result.assistant_message.split():
                yield ChatStreamEvent(event="assistant_delta", data={"delta": f"{token} "})
            if result.tool_payload is not None:
                yield ChatStreamEvent(
                    event="tool_status",
                    data=self._build_tool_status_payload(result),
                )
            yield ChatStreamEvent(
                event="final",
                data=self._serialize_chat_turn_response(result),
            )
        except LLMConfigurationError as exc:
            yield ChatStreamEvent(
                event="error",
                data={
                    "message": str(exc),
                    "status": int(HTTPStatus.SERVICE_UNAVAILABLE),
                    "request_id": request_id,
                },
            )
        except ValueError as exc:
            yield ChatStreamEvent(
                event="error",
                data={
                    "message": str(exc) or "Provider unavailable.",
                    "status": int(HTTPStatus.BAD_REQUEST),
                    "request_id": request_id,
                },
            )
        except Exception as exc:
            yield ChatStreamEvent(
                event="error",
                data={
                    "message": str(exc) or "Unexpected server error while streaming response.",
                    "status": int(HTTPStatus.INTERNAL_SERVER_ERROR),
                    "request_id": request_id,
                },
            )
    
    # -------------------------------------------------------------------------
    def _build_tool_status_payload(self, response: ChatTurnResponse) -> dict[str, Any]:
        tool_payload = response.tool_payload
        if not isinstance(tool_payload, dict):
            return {"available": False}
        satellite_imagery = tool_payload.get("satellite_imagery")
        map_session = tool_payload.get("map_session")
        overlay_count = 0
        if isinstance(map_session, dict):
            overlays = map_session.get("overlays")
            if isinstance(overlays, list):
                overlay_count = len(overlays)
        return {
            "available": True,
            "execution": tool_payload.get("execution"),
            "has_satellite_imagery": isinstance(satellite_imagery, dict),
            "has_map_session": isinstance(map_session, dict),
            "overlay_count": overlay_count,
        }

    @staticmethod
    def _serialize_chat_turn_response(response: ChatTurnResponse) -> dict[str, Any]:
        return {
            "session_id": response.session_id,
            "request_id": response.request_id,
            "assistant_message": response.assistant_message,
            "turn_contract": response.turn_contract.model_dump(mode="json"),
            "decision": response.decision.model_dump(mode="json"),
            "map_session": response.map_session.model_dump(mode="json")
            if response.map_session is not None
            else None,
            "tool_payload": response.tool_payload,
            "memory_snapshot": response.memory_snapshot,
            "context_usage": response.context_usage.model_dump(mode="json")
            if response.context_usage is not None
            else None,
        }
