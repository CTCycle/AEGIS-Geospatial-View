from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from server.repositories.database.backend import get_database
from server.repositories.schemas.models import (
    Base,
    ChatSessionRecord,
    ConversationContextRecord,
    ConversationRecord,
)

###############################################################################
class ConversationContextRepository:

    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        backend = get_database().backend
        Base.metadata.create_all(backend.engine)
        self._session_factory = backend.session

    # -------------------------------------------------------------------------
    def get_or_create(self, conversation_id: str) -> ConversationContextRecord:
        """Resolve a conversation's durable context, lazily linking legacy rows."""
        with self._session_factory() as session:
            context = session.get(ConversationContextRecord, conversation_id)
            if context is not None:
                return context
            conversation = session.get(ConversationRecord, conversation_id)
            if conversation is None:
                raise ValueError("Conversation not found.")
            chat_session = ChatSessionRecord(
                title=conversation.title,
                status="active",
            )
            session.add(chat_session)
            session.flush()
            context = ConversationContextRecord(
                conversation_id=conversation_id,
                chat_session_id=chat_session.id,
            )
            session.add(context)
            session.commit()
            session.refresh(context)
            return context

    # -------------------------------------------------------------------------
    def resolve_chat_session_id(self, conversation_id: str) -> int:
        return self.get_or_create(conversation_id).chat_session_id

    # -------------------------------------------------------------------------
    def validate_session(self, conversation_id: str, chat_session_id: int) -> None:
        with self._session_factory() as session:
            statement = select(ConversationContextRecord).where(
                ConversationContextRecord.conversation_id == conversation_id,
                ConversationContextRecord.chat_session_id == chat_session_id,
            )
            if session.execute(statement).scalars().first() is None:
                raise ValueError("Chat session does not belong to conversation.")

    # -------------------------------------------------------------------------
    def read_state(self, conversation_id: str) -> dict[str, Any]:
        context = self.get_or_create(conversation_id)
        return {
            "context_revision": context.context_revision,
            "active_instructions": self._decode(context.active_instructions_json, []),
            "task_snapshot": self._decode(context.task_snapshot_json, None),
            "memory_snapshot": self._decode(context.memory_snapshot_json, {}),
            "conversation_summary": self._decode(context.conversation_summary_json, None),
            "summary_through_turn_index": context.summary_through_turn_index,
        }

    # -------------------------------------------------------------------------
    def write_state(
        self,
        conversation_id: str,
        *,
        expected_revision: int,
        active_instructions: list[dict[str, Any]] | None = None,
        task_snapshot: dict[str, Any] | None = None,
        memory_snapshot: dict[str, Any] | None = None,
        conversation_summary: dict[str, Any] | None = None,
        summary_through_turn_index: int | None = None,
    ) -> int:
        self.get_or_create(conversation_id)
        with self._session_factory() as session:
            context = session.get(ConversationContextRecord, conversation_id)
            if context is None:
                raise ValueError("Conversation context not found.")
            if context.context_revision != expected_revision:
                raise ValueError("Conversation context revision conflict.")
            if active_instructions is not None:
                context.active_instructions_json = json.dumps(active_instructions, default=str)
            if task_snapshot is not None:
                context.task_snapshot_json = json.dumps(task_snapshot, default=str)
            if memory_snapshot is not None:
                context.memory_snapshot_json = json.dumps(memory_snapshot, default=str)
            if conversation_summary is not None:
                context.conversation_summary_json = json.dumps(conversation_summary, default=str)
            if summary_through_turn_index is not None:
                context.summary_through_turn_index = summary_through_turn_index
            context.context_revision += 1
            context.updated_at = datetime.now(UTC)
            session.commit()
            return context.context_revision

    # -------------------------------------------------------------------------
    @staticmethod
    def _decode(value: str | None, fallback: Any) -> Any:
        if not value:
            return fallback
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return fallback
