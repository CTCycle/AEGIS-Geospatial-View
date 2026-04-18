from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

from AEGIS.server.configurations import get_server_settings
from AEGIS.server.repositories.chat_history import ChatHistoryRepository


###############################################################################
class ChatHistoryBuffer:
    def __init__(
        self,
        *,
        history_repo: ChatHistoryRepository,
        max_messages: int | None = None,
    ) -> None:
        self.history_repo = history_repo
        self.max_messages = (
            max_messages or get_server_settings().chat.max_history_messages
        )
        self._buffers: dict[int, deque[dict[str, Any]]] = defaultdict(
            lambda: deque(maxlen=self.max_messages)
        )

    # -------------------------------------------------------------------------
    def get_or_hydrate(self, session_id: int) -> list[dict[str, Any]]:
        if session_id not in self._buffers or not self._buffers[session_id]:
            messages = self.history_repo.list_recent_messages(
                session_id=session_id,
                limit=self.max_messages,
            )
            hydrated = deque(messages, maxlen=self.max_messages)
            self._buffers[session_id] = hydrated
        return list(self._buffers[session_id])

    # -------------------------------------------------------------------------
    def append(self, session_id: int, message: dict[str, Any]) -> None:
        if session_id not in self._buffers:
            hydrated = self.history_repo.list_recent_messages(
                session_id=session_id,
                limit=self.max_messages,
            )
            self._buffers[session_id] = deque(hydrated, maxlen=self.max_messages)
        existing = self._buffers[session_id]
        message_id = message.get("id")
        if message_id is not None and any(
            entry.get("id") == message_id for entry in existing
        ):
            return
        existing.append(message)

    # -------------------------------------------------------------------------
    def list_recent(self, session_id: int) -> list[dict[str, Any]]:
        return list(self._buffers.get(session_id, deque()))

    # -------------------------------------------------------------------------
    def list_scoped(self, session_id: int, *, start_index: int) -> list[dict[str, Any]]:
        messages = self.list_recent(session_id)
        if start_index <= 0:
            return messages
        return messages[start_index:]

    # -------------------------------------------------------------------------
    def reset(self, session_id: int) -> None:
        self._buffers.pop(session_id, None)
