from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select

from server.repositories.database.backend import get_database
from server.repositories.schemas.models import (
    Base,
    ChatSessionRecord,
    ConversationContextRecord,
    ConversationRecord,
)

###############################################################################
class ConversationRepository:

    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        backend = get_database().backend
        Base.metadata.create_all(backend.engine)
        self._session_factory = backend.session

    # -------------------------------------------------------------------------
    def create_conversation(
        self,
        title: str | None,
        owner_user_id: str | None = None,
    ) -> ConversationRecord:
        with self._session_factory() as session:
            record = ConversationRecord(
                id=f"conv_{uuid4().hex}",
                owner_user_id=owner_user_id,
                title=title.strip() if isinstance(title, str) and title.strip() else None,
            )
            session.add(record)
            session.flush()
            chat_session = ChatSessionRecord(title=record.title, status="active")
            session.add(chat_session)
            session.flush()
            session.add(
                ConversationContextRecord(
                    conversation_id=record.id,
                    chat_session_id=chat_session.id,
                )
            )
            session.commit()
            session.refresh(record)
            return record

    # -------------------------------------------------------------------------
    def get_conversation(self, conversation_id: str) -> ConversationRecord | None:
        with self._session_factory() as session:
            return session.get(ConversationRecord, conversation_id)

    # -------------------------------------------------------------------------
    def set_active_run(self, conversation_id: str, run_id: str | None) -> None:
        with self._session_factory() as session:
            record = session.get(ConversationRecord, conversation_id)
            if record is None:
                raise ValueError("Conversation not found.")
            record.active_run_id = run_id
            record.updated_at = datetime.now(UTC)
            session.commit()

    # -------------------------------------------------------------------------
    def verify_conversation_access(
        self,
        conversation_id: str,
        owner_user_id: str | None = None,
    ) -> ConversationRecord:
        record = self.get_conversation(conversation_id)
        if record is None:
            raise ValueError("Conversation not found.")
        if record.owner_user_id is not None and record.owner_user_id != owner_user_id:
            raise PermissionError("Conversation access denied.")
        return record

    # -------------------------------------------------------------------------
    def list_conversations(self) -> list[ConversationRecord]:
        with self._session_factory() as session:
            return list(session.execute(select(ConversationRecord)).scalars().all())
