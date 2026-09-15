from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select, update

from server.domain.agent.conversation import ConversationState
from server.repositories.database.sqlite import SQLiteRepository
from server.repositories.schemas.models import ConversationRecord

###############################################################################
class ConversationRepository:

    # -------------------------------------------------------------------------
    def __init__(self, database: SQLiteRepository) -> None:
        self._session_factory = database.session

    # -------------------------------------------------------------------------
    def create_conversation(
        self, title: str | None, owner_user_id: str | None = None
    ) -> ConversationRecord:
        with self._session_factory() as session:
            conversation_id = f"conv_{uuid4().hex}"
            record = ConversationRecord(
                id=conversation_id,
                owner_user_id=owner_user_id,
                title=title.strip()
                if isinstance(title, str) and title.strip()
                else None,
                conversation_state=ConversationState.empty(
                    conversation_id, revision=1
                ).model_dump(mode="json"),
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
            "conversation_state": record.conversation_state,
        }

    # -------------------------------------------------------------------------
    def write_state(
        self,
        conversation_id: str,
        *,
        expected_revision: int,
        conversation_state: dict[str, Any],
    ) -> int:
        values: dict[str, Any] = {
            "context_revision": ConversationRecord.context_revision + 1,
            "updated_at": datetime.now(UTC),
            "conversation_state": conversation_state,
        }
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
