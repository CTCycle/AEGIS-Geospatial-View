from __future__ import annotations

from collections.abc import AsyncIterator
from http import HTTPStatus
from typing import Any

from server.domain.chat import ChatStreamEvent, ChatTurnRequest, ChatTurnResponse
from server.services.agent.orchestrator import AgentOrchestrator
from server.services.llm.errors import LLMConfigurationError

###############################################################################
class ChatStreamingService:

    # -------------------------------------------------------------------------
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
            yield ChatStreamEvent(event="parsed", data=self._build_parsed_payload(result))
            yield ChatStreamEvent(event="policy", data=self._build_policy_payload(result))
            for event in self._build_tool_lifecycle_events(result):
                yield event
            if result.map_session is not None:
                yield ChatStreamEvent(
                    event="map_session_created",
                    data={
                        "request_id": result.request_id,
                        "session_id": result.session_id,
                        "map_session": result.map_session.model_dump(mode="json"),
                    },
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
    @staticmethod
    def _build_parsed_payload(response: ChatTurnResponse) -> dict[str, Any]:
        return {
            "request_id": response.request_id,
            "session_id": response.session_id,
            "task_class": response.turn_contract.task_class,
            "action_id": response.turn_contract.normalized_action.action_id,
            "requires_location": response.turn_contract.normalized_action.requires_location,
            "location_signal_count": len(response.turn_contract.location_signals),
            "ambiguities": list(response.turn_contract.ambiguities),
        }

    # -------------------------------------------------------------------------
    @staticmethod
    def _build_policy_payload(response: ChatTurnResponse) -> dict[str, Any]:
        return {
            "request_id": response.request_id,
            "session_id": response.session_id,
            "state": response.decision.plan.state,
            "mode": response.decision.plan.mode,
            "action_id": response.decision.plan.action_id,
            "trace_steps": list(response.decision.trace.steps),
            "has_clarification": response.decision.clarification is not None,
        }

    # -------------------------------------------------------------------------
    @staticmethod
    def _build_tool_lifecycle_events(response: ChatTurnResponse) -> list[ChatStreamEvent]:
        tool_payload = response.tool_payload
        if not isinstance(tool_payload, dict):
            return []
        tool_calls = tool_payload.get("tool_calls")
        tool_results = tool_payload.get("tool_results")
        if not isinstance(tool_calls, list) or not isinstance(tool_results, list):
            return []

        result_by_call_id: dict[str, dict[str, Any]] = {}
        for result in tool_results:
            if not isinstance(result, dict):
                continue
            tool_call_id = result.get("tool_call_id")
            if isinstance(tool_call_id, str):
                result_by_call_id[tool_call_id] = result

        events: list[ChatStreamEvent] = []
        for tool_call in tool_calls:
            if not isinstance(tool_call, dict):
                continue
            tool_call_id = tool_call.get("id")
            if not isinstance(tool_call_id, str):
                continue
            events.append(
                ChatStreamEvent(
                    event="tool_call_started",
                    data={
                        "request_id": response.request_id,
                        "session_id": response.session_id,
                        "tool_call_id": tool_call_id,
                        "name": tool_call.get("name"),
                        "arguments": tool_call.get("arguments"),
                    },
                )
            )
            tool_result = result_by_call_id.get(tool_call_id)
            if tool_result is None:
                continue
            events.append(
                ChatStreamEvent(
                    event="tool_call_completed",
                    data={
                        "request_id": response.request_id,
                        "session_id": response.session_id,
                        "tool_call_id": tool_call_id,
                        "name": tool_result.get("name") or tool_call.get("name"),
                        "ok": bool(not tool_result.get("is_error")),
                        "error": tool_result.get("error"),
                        "content": tool_result.get("content"),
                    },
                )
            )
        return events

    # -------------------------------------------------------------------------
    @staticmethod
    def _serialize_chat_turn_response(response: ChatTurnResponse) -> dict[str, Any]:
        return {
            "session_id": response.session_id,
            "request_id": response.request_id,
            "assistant_message": response.assistant_message,
            "turn_contract": response.turn_contract.model_dump(mode="json"),
            "decision": response.decision.model_dump(mode="json"),
            "operation": response.operation.model_dump(mode="json")
            if response.operation is not None
            else None,
            "map_session": response.map_session.model_dump(mode="json")
            if response.map_session is not None
            else None,
            "tool_payload": response.tool_payload,
            "memory_snapshot": response.memory_snapshot,
            "context_usage": response.context_usage.model_dump(mode="json")
            if response.context_usage is not None
            else None,
        }
