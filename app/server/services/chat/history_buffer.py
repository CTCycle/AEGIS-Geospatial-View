from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

from server.configurations import get_server_settings
from server.repositories.chat_history import ChatHistoryRepository

###############################################################################
class ChatHistoryBuffer:

    # -------------------------------------------------------------------------
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
        self._buffers: dict[str, deque[dict[str, Any]]] = defaultdict(
            lambda: deque(maxlen=self.max_messages)
        )

    # -------------------------------------------------------------------------
    def get_or_hydrate(self, conversation_id: str) -> list[dict[str, Any]]:
        if conversation_id not in self._buffers or not self._buffers[conversation_id]:
            messages = self.history_repo.list_recent_messages(
                conversation_id=conversation_id,
                limit=self.max_messages,
            )
            hydrated = deque(messages, maxlen=self.max_messages)
            self._buffers[conversation_id] = hydrated
        return list(self._buffers[conversation_id])

    # -------------------------------------------------------------------------
    def append(self, conversation_id: str, message: dict[str, Any]) -> None:
        if conversation_id not in self._buffers:
            hydrated = self.history_repo.list_recent_messages(
                conversation_id=conversation_id,
                limit=self.max_messages,
            )
            self._buffers[conversation_id] = deque(hydrated, maxlen=self.max_messages)
        existing = self._buffers[conversation_id]
        message_id = message.get("id")
        if message_id is not None and any(
            entry.get("id") == message_id for entry in existing
        ):
            return
        existing.append(message)

    # -------------------------------------------------------------------------
    def list_recent(self, conversation_id: str) -> list[dict[str, Any]]:
        return list(self._buffers.get(conversation_id, deque()))

    # -------------------------------------------------------------------------
    def list_scoped(self, conversation_id: str, *, start_index: int) -> list[dict[str, Any]]:
        messages = self.list_recent(conversation_id)
        if start_index <= 0:
            return messages
        return messages[start_index:]

    # -------------------------------------------------------------------------
    def reset(self, conversation_id: str) -> None:
        self._buffers.pop(conversation_id, None)
