from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc, select, update

from server.repositories.database.backend import get_database
from server.repositories.schemas.models import Base, ChatMessageRecord, ConversationRecord


###############################################################################
class ChatHistoryRepository:

    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        backend = get_database().backend
        Base.metadata.create_all(backend.engine)
        self._session_factory = backend.session

    # -------------------------------------------------------------------------
    @staticmethod
    def _to_message_dict(row: ChatMessageRecord) -> dict[str, Any]:
        return {
            "id": row.id,
            "conversation_id": row.conversation_id,
            "turn_index": row.turn_index,
            "request_id": row.request_id,
            "role": row.role,
            "content": row.content,
            "structured_payload": row.structured_payload,
            "tool_payload": row.tool_payload,
            "map_session": row.map_session,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    # -------------------------------------------------------------------------
    def append_message(
        self,
        *,
        conversation_id: str,
        role: str,
        content: str,
        request_id: str | None = None,
        structured_payload: Any = None,
        tool_payload: Any = None,
        map_session: Any = None,
    ) -> ChatMessageRecord:
        with self._session_factory() as session:
            turn_index = session.scalar(
                update(ConversationRecord)
                .where(ConversationRecord.id == conversation_id)
                .values(
                    next_message_sequence=ConversationRecord.next_message_sequence + 1,
                    updated_at=datetime.now(UTC),
                )
                .returning(ConversationRecord.next_message_sequence)
            )
            if turn_index is None:
                raise ValueError("Conversation not found.")
            payload = self._with_request_id(structured_payload, request_id)
            message = ChatMessageRecord(
                conversation_id=conversation_id,
                turn_index=turn_index,
                request_id=request_id,
                role=role,
                content=content,
                structured_payload=payload,
                tool_payload=tool_payload,
                map_session=map_session,
            )
            session.add(message)
            session.commit()
            session.refresh(message)
            return message

    # -------------------------------------------------------------------------
    @staticmethod
    def _with_request_id(structured_payload: Any, request_id: str | None) -> Any:
        if request_id is None:
            return structured_payload
        if structured_payload is None:
            return {"request_id": request_id}
        if isinstance(structured_payload, dict):
            payload = dict(structured_payload)
            payload.setdefault("request_id", request_id)
            return payload
        return structured_payload

    # -------------------------------------------------------------------------
    def _last_assistant_payload(self, conversation_id: str) -> dict[str, Any] | None:
        row = self.get_last_assistant_message(conversation_id)
        payload = row.get("structured_payload") if row else None
        return payload if isinstance(payload, dict) else None

    # -------------------------------------------------------------------------
    def list_recent_messages(self, conversation_id: str, limit: int) -> list[dict[str, Any]]:
        with self._session_factory() as session:
            statement = (
                select(ChatMessageRecord)
                .where(ChatMessageRecord.conversation_id == conversation_id)
                .order_by(ChatMessageRecord.turn_index.desc())
                .limit(max(1, limit))
            )
            rows = list(reversed(session.execute(statement).scalars().all()))
        return [self._to_message_dict(row) for row in rows]

    # -------------------------------------------------------------------------
    def get_last_assistant_message(self, conversation_id: str) -> dict[str, Any] | None:
        with self._session_factory() as session:
            row = session.execute(
                select(ChatMessageRecord)
                .where(
                    ChatMessageRecord.conversation_id == conversation_id,
                    ChatMessageRecord.role == "assistant",
                )
                .order_by(desc(ChatMessageRecord.turn_index))
                .limit(1)
            ).scalars().first()
        return self._to_message_dict(row) if row is not None else None

    # -------------------------------------------------------------------------
    def find_message_by_request_id(
        self, *, conversation_id: str, role: str, request_id: str
    ) -> dict[str, Any] | None:
        with self._session_factory() as session:
            row = session.execute(
                select(ChatMessageRecord).where(
                    ChatMessageRecord.conversation_id == conversation_id,
                    ChatMessageRecord.role == role,
                    ChatMessageRecord.request_id == request_id,
                )
            ).scalars().first()
        return self._to_message_dict(row) if row is not None else None

    # -------------------------------------------------------------------------
    def list_messages(self, *, conversation_id: str) -> list[dict[str, Any]]:
        with self._session_factory() as session:
            rows = session.execute(
                select(ChatMessageRecord)
                .where(ChatMessageRecord.conversation_id == conversation_id)
                .order_by(ChatMessageRecord.turn_index.asc())
            ).scalars().all()
        return [self._to_message_dict(row) for row in rows]
