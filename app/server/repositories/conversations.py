from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select, update

from server.repositories.database.backend import get_database
from server.repositories.schemas.models import Base, ConversationRecord

###############################################################################
class ConversationRepository:

    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        backend = get_database().backend
        Base.metadata.create_all(backend.engine)
        self._session_factory = backend.session

    # -------------------------------------------------------------------------
    def create_conversation(
        self, title: str | None, owner_user_id: str | None = None
    ) -> ConversationRecord:
        with self._session_factory() as session:
            record = ConversationRecord(
                id=f"conv_{uuid4().hex}",
                owner_user_id=owner_user_id,
                title=title.strip() if isinstance(title, str) and title.strip() else None,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    # -------------------------------------------------------------------------
    def get_conversation(self, conversation_id: str) -> ConversationRecord | None:
        with self._session_factory() as session:
            return session.get(ConversationRecord, conversation_id)

    # -------------------------------------------------------------------------
    def read_state(self, conversation_id: str) -> dict[str, Any]:
        record = self._require(conversation_id)
        return {
            "context_revision": record.context_revision,
            "active_instructions": record.active_instructions or [],
            "task_snapshot": record.task_snapshot,
            "memory_snapshot": record.memory_snapshot or {},
            "conversation_summary": record.conversation_summary,
            "summary_through_turn_index": record.summary_through_turn_index,
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
        values: dict[str, Any] = {
            "context_revision": ConversationRecord.context_revision + 1,
            "updated_at": datetime.now(UTC),
        }
        for name, value in (
            ("active_instructions", active_instructions),
            ("task_snapshot", task_snapshot),
            ("memory_snapshot", memory_snapshot),
            ("conversation_summary", conversation_summary),
            ("summary_through_turn_index", summary_through_turn_index),
        ):
            if value is not None:
                values[name] = value
        with self._session_factory() as session:
            revision = session.scalar(
                update(ConversationRecord)
                .where(
                    ConversationRecord.id == conversation_id,
                    ConversationRecord.context_revision == expected_revision,
                )
                .values(**values)
                .returning(ConversationRecord.context_revision)
            )
            if revision is None:
                raise ValueError("Conversation context revision conflict.")
            session.commit()
            return int(revision)

    # -------------------------------------------------------------------------
    def verify_conversation_access(
        self, conversation_id: str, owner_user_id: str | None = None
    ) -> ConversationRecord:
        record = self._require(conversation_id)
        if record.owner_user_id is not None and record.owner_user_id != owner_user_id:
            raise PermissionError("Conversation access denied.")
        return record

    # -------------------------------------------------------------------------
    def list_conversations(self) -> list[ConversationRecord]:
        with self._session_factory() as session:
            return list(session.execute(select(ConversationRecord)).scalars().all())

    # -------------------------------------------------------------------------
    def _require(self, conversation_id: str) -> ConversationRecord:
        record = self.get_conversation(conversation_id)
        if record is None:
            raise ValueError("Conversation not found.")
        return record
