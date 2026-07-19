from __future__ import annotations

from typing import Any

from server.repositories.chat_history import ChatHistoryRepository

###############################################################################
class ChatHistoryService:

    # -------------------------------------------------------------------------
    def __init__(self, repo: ChatHistoryRepository | None = None) -> None:
        self.repo = repo or ChatHistoryRepository()

    # -------------------------------------------------------------------------
    def append_message(self, **kwargs: Any) -> None:
        self.repo.append_message(**kwargs)

    # -------------------------------------------------------------------------
    def list_recent_messages(self, conversation_id: str, limit: int) -> list[dict[str, Any]]:
        return self.repo.list_recent_messages(conversation_id, limit)

    # -------------------------------------------------------------------------
    def list_messages(self, *, conversation_id: str) -> list[dict[str, Any]]:
        return self.repo.list_messages(conversation_id=conversation_id)

    # -------------------------------------------------------------------------
    def get_latest_turn_contract(self, conversation_id: str) -> dict[str, Any] | None:
        last = self.repo.get_last_assistant_message(conversation_id)
        payload = last.get("structured_payload") if last else None
        contract = payload.get("turn_contract") if isinstance(payload, dict) else None
        return contract if isinstance(contract, dict) else None

    # -------------------------------------------------------------------------
    def get_latest_memory_snapshot(self, conversation_id: str) -> dict[str, Any]:
        last = self.repo.get_last_assistant_message(conversation_id)
        payload = last.get("structured_payload") if last else None
        snapshot = payload.get("memory_snapshot") if isinstance(payload, dict) else None
        return snapshot if isinstance(snapshot, dict) else {"location_slots": [], "active_location": None}

    # -------------------------------------------------------------------------
    def find_message_by_request_id(
        self, *, conversation_id: str, role: str, request_id: str
    ) -> dict[str, Any] | None:
        return self.repo.find_message_by_request_id(
            conversation_id=conversation_id, role=role, request_id=request_id
        )
