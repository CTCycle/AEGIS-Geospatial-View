from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import desc, func, select

from AEGIS.server.domain.extraction.models import ExtractedIntent
from AEGIS.server.repositories.database.backend import get_database
from AEGIS.server.repositories.schemas.models import (
    Base,
    ChatMessageRecord,
    ChatSessionRecord,
)


###############################################################################
def _to_json_payload(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, default=str)


###############################################################################
def _from_json_payload(value: str | None) -> Any:
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


class ChatHistoryRepository:
    def __init__(self) -> None:
        backend = get_database().backend
        Base.metadata.create_all(backend.engine)
        self._session_factory = backend.session

    def _to_message_dict(self, row: ChatMessageRecord) -> dict[str, Any]:
        return {
            "id": row.id,
            "session_id": row.session_id,
            "turn_index": row.turn_index,
            "role": row.role,
            "content": row.content,
            "structured_payload": _from_json_payload(row.structured_payload_json),
            "tool_payload": _from_json_payload(row.tool_payload_json),
            "map_session": _from_json_payload(row.map_session_json),
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    def create_session(self, *, title: str | None = None) -> ChatSessionRecord:
        with self._session_factory() as session:
            record = ChatSessionRecord(title=title, status="active")
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    def get_session(self, session_id: int) -> ChatSessionRecord | None:
        with self._session_factory() as session:
            statement = select(ChatSessionRecord).where(
                ChatSessionRecord.id == session_id
            )
            return session.execute(statement).scalars().first()

    def upsert_session(
        self, session_id: int | None, *, title: str | None = None
    ) -> ChatSessionRecord:
        if session_id is None:
            return self.create_session(title=title)
        with self._session_factory() as session:
            statement = select(ChatSessionRecord).where(
                ChatSessionRecord.id == session_id
            )
            record = session.execute(statement).scalars().first()
            if record is None:
                record = ChatSessionRecord(id=session_id, title=title, status="active")
                session.add(record)
                session.commit()
                session.refresh(record)
                return record
            if title:
                record.title = title
            record.updated_at = datetime.utcnow()
            session.commit()
            session.refresh(record)
            return record

    def append_message(
        self,
        *,
        session_id: int,
        role: str,
        content: str,
        structured_payload: Any = None,
        tool_payload: Any = None,
        map_session: Any = None,
    ) -> ChatMessageRecord:
        with self._session_factory() as session:
            count_statement = (
                select(func.count())
                .select_from(ChatMessageRecord)
                .where(ChatMessageRecord.session_id == session_id)
            )
            turn_index = int(session.scalar(count_statement) or 0)
            message = ChatMessageRecord(
                session_id=session_id,
                turn_index=turn_index,
                role=role,
                content=content,
                structured_payload_json=_to_json_payload(structured_payload),
                tool_payload_json=_to_json_payload(tool_payload),
                map_session_json=_to_json_payload(map_session),
            )
            session.add(message)
            session_record = session.get(ChatSessionRecord, session_id)
            if session_record is not None:
                session_record.updated_at = datetime.utcnow()
                if map_session is not None:
                    session_record.last_map_session_json = _to_json_payload(map_session)
            session.commit()
            session.refresh(message)
            return message

    def list_recent_messages(self, session_id: int, limit: int) -> list[dict[str, Any]]:
        with self._session_factory() as session:
            statement = (
                select(ChatMessageRecord)
                .where(ChatMessageRecord.session_id == session_id)
                .order_by(ChatMessageRecord.turn_index.desc())
                .limit(max(1, limit))
            )
            rows = list(reversed(session.execute(statement).scalars().all()))
        return [self._to_message_dict(row) for row in rows]

    def get_latest_extracted_state(self, session_id: int) -> Any | None:
        with self._session_factory() as session:
            statement = (
                select(ChatMessageRecord)
                .where(
                    ChatMessageRecord.session_id == session_id,
                    ChatMessageRecord.role == "assistant",
                )
                .order_by(desc(ChatMessageRecord.turn_index))
                .limit(1)
            )
            row = session.execute(statement).scalars().first()
        if row is None:
            return None
        payload = _from_json_payload(row.structured_payload_json)
        if not isinstance(payload, dict):
            return None

        extracted_state_payload = payload.get("extracted_state")
        if not isinstance(extracted_state_payload, dict):
            return None

        try:
            return ExtractedIntent.model_validate(extracted_state_payload)
        except Exception:
            return None

    def get_last_assistant_message(self, session_id: int) -> dict[str, Any] | None:
        with self._session_factory() as session:
            statement = (
                select(ChatMessageRecord)
                .where(
                    ChatMessageRecord.session_id == session_id,
                    ChatMessageRecord.role == "assistant",
                )
                .order_by(desc(ChatMessageRecord.turn_index))
                .limit(1)
            )
            row = session.execute(statement).scalars().first()
        if row is None:
            return None
        return self._to_message_dict(row)

    def list_messages(self, *, session_id: int) -> list[dict[str, Any]]:
        with self._session_factory() as session:
            statement = (
                select(ChatMessageRecord)
                .where(ChatMessageRecord.session_id == session_id)
                .order_by(ChatMessageRecord.turn_index.asc())
            )
            rows = session.execute(statement).scalars().all()
            return [self._to_message_dict(row) for row in rows]
