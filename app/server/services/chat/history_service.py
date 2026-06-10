from __future__ import annotations

from typing import Any

from server.repositories.chat_history import ChatHistoryRepository


class ChatHistoryService:
    def __init__(
        self, repo: ChatHistoryRepository | None = None
    ) -> None:
        self.repo = repo or ChatHistoryRepository()

    def create_session(self, *, title: str | None = None) -> Any:
        return self.repo.create_session(title=title)

    def get_session(self, session_id: int) -> Any | None:
        return self.repo.get_session(session_id)

    def upsert_session(
        self, session_id: int | None, *, title: str | None = None
    ) -> Any:
        return self.repo.upsert_session(session_id, title=title)

    def append_message(
        self,
        *,
        session_id: int,
        role: str,
        content: str,
        request_id: str | None = None,
        structured_payload: Any = None,
        tool_payload: Any = None,
        map_session: Any = None,
    ) -> None:
        self.repo.append_message(
            session_id=session_id,
            role=role,
            content=content,
            request_id=request_id,
            structured_payload=structured_payload,
            tool_payload=tool_payload,
            map_session=map_session,
        )

    def list_recent_messages(
        self, session_id: int, limit: int
    ) -> list[dict[str, Any]]:
        return self.repo.list_recent_messages(session_id, limit)

    def list_messages(self, *, session_id: int) -> list[dict[str, Any]]:
        return self.repo.list_messages(session_id=session_id)

    def get_last_assistant_message(
        self, session_id: int
    ) -> dict[str, Any] | None:
        return self.repo.get_last_assistant_message(session_id)

    def get_latest_turn_contract(self, session_id: int) -> dict[str, Any] | None:
        last = self.repo.get_last_assistant_message(session_id)
        if last is None:
            return None
        payload = last.get("structured_payload")
        if not isinstance(payload, dict):
            return None
        contract = payload.get("turn_contract")
        return contract if isinstance(contract, dict) else None

    def get_latest_memory_snapshot(self, session_id: int) -> dict[str, Any]:
        last = self.repo.get_last_assistant_message(session_id)
        if last is None:
            return {"location_slots": [], "active_location": None}
        payload = last.get("structured_payload")
        if not isinstance(payload, dict):
            return {"location_slots": [], "active_location": None}
        snapshot = payload.get("memory_snapshot")
        if not isinstance(snapshot, dict):
            return {"location_slots": [], "active_location": None}
        return snapshot

    def find_message_by_request_id(
        self,
        *,
        session_id: int,
        role: str,
        request_id: str,
    ) -> dict[str, Any] | None:
        messages = self.repo.list_messages(session_id=session_id)
        for msg in messages:
            if msg.get("role") != role:
                continue
            payload = msg.get("structured_payload")
            if isinstance(payload, dict) and payload.get("request_id") == request_id:
                return msg
        return None
