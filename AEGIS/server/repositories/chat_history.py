from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import select

from AEGIS.server.repositories.database.backend import get_database
from AEGIS.server.repositories.schemas.models import ChatMessageRecord, ChatSessionRecord


def _to_json_payload(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value)


def _from_json_payload(value: str | None) -> Any:
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


class ChatHistoryRepository:
    def __init__(self) -> None:
        self._session_factory = get_database().backend.session

    def create_session(self, *, title: str | None = None) -> ChatSessionRecord:
        with self._session_factory() as session:
            record = ChatSessionRecord(title=title, status="active")
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    def get_session(self, session_id: int) -> ChatSessionRecord | None:
        with self._session_factory() as session:
            statement = select(ChatSessionRecord).where(ChatSessionRecord.id == session_id)
            return session.execute(statement).scalars().first()

    def upsert_session(self, session_id: int | None, *, title: str | None = None) -> ChatSessionRecord:
        if session_id is None:
            return self.create_session(title=title)
        with self._session_factory() as session:
            statement = select(ChatSessionRecord).where(ChatSessionRecord.id == session_id)
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
            count_statement = select(ChatMessageRecord).where(
                ChatMessageRecord.session_id == session_id
            )
            turn_index = len(session.execute(count_statement).scalars().all())
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

    def list_messages(self, *, session_id: int) -> list[dict[str, Any]]:
        with self._session_factory() as session:
            statement = (
                select(ChatMessageRecord)
                .where(ChatMessageRecord.session_id == session_id)
                .order_by(ChatMessageRecord.turn_index.asc())
            )
            rows = session.execute(statement).scalars().all()
            return [
                {
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
                for row in rows
            ]
