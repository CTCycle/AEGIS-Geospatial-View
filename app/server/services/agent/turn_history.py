from __future__ import annotations

from server.common.typing import is_json_object, json_object

from typing import Any

from server.contracts.chat import ChatTurnResponse
from server.contracts.extraction import LocationSignal
from server.services.agent.location_memory import LocationMemoryService
from server.services.chat.history_service import ChatHistoryService

###############################################################################
class AgentTurnHistoryService:

    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        history_service: ChatHistoryService,
        location_memory_service: LocationMemoryService,
    ) -> None:
        self.history_service = history_service
        self.location_memory_service = location_memory_service

    # -------------------------------------------------------------------------
    def load_existing_response(
        self,
        conversation_id: str,
        request_id: str,
    ) -> ChatTurnResponse | None:
        existing = self.history_service.find_message_by_request_id(
            conversation_id=conversation_id,
            role="assistant",
            request_id=request_id,
        )
        if existing is None:
            return None
        payload = json_object(existing.get("structured_payload"))
        if not payload:
            return None
        response_payload: dict[str, Any] = {
            "request_id": request_id,
            "conversation_id": conversation_id,
            "assistant_message": existing.get("content") or "",
            "turn_contract": payload.get("turn_contract"),
            "decision": payload.get("decision"),
            "operation": payload.get("operation"),
            "tool_payload": existing.get("tool_payload"),
            "map_session": existing.get("map_session"),
            "memory_snapshot": payload.get("memory_snapshot") or {},
            "context_usage": payload.get("context_usage"),
        }
        return ChatTurnResponse.model_validate(response_payload)

    # -------------------------------------------------------------------------
    @staticmethod
    def merge_conversation_state_memory(
        latest_memory: dict[str, Any] | None,
        active_visualization: dict[str, Any] | None,
    ) -> dict[str, Any]:
        merged = dict(latest_memory or {})
        if not is_json_object(active_visualization):
            return merged
        merged["active_visualization"] = active_visualization
        location = active_visualization.get("resolved_location")
        if is_json_object(location):
            merged["active_location"] = location
        return merged

    # -------------------------------------------------------------------------
    def merge_memory_location_signals(
        self,
        *,
        turn_contract: Any,
        latest_memory: dict[str, Any] | None,
    ) -> Any:
        latest_memory = json_object(latest_memory)
        memory_signals = self.location_memory_service.resolve_explicit_references(
            list(turn_contract.location_signals),
            latest_memory,
        )
        if not memory_signals:
            return turn_contract
        merged_signals = self.dedupe_location_signals(
            [*memory_signals, *list(turn_contract.location_signals)]
        )
        ambiguities = [
            item
            for item in turn_contract.ambiguities
            if item not in {"missing_location", "deictic_without_memory"}
        ]
        return turn_contract.model_copy(
            update={
                "location_signals": merged_signals,
                "ambiguities": ambiguities,
            }
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def dedupe_location_signals(signals: list[LocationSignal]) -> list[LocationSignal]:
        unique: list[LocationSignal] = []
        seen: set[tuple[str, str, float | None, float | None, str]] = set()
        for signal in signals:
            key = (
                signal.signal_type,
                signal.normalized_value or signal.raw_value,
                signal.latitude,
                signal.longitude,
                signal.source,
            )
            if key in seen:
                continue
            seen.add(key)
            unique.append(signal)
        return unique
