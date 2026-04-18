from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from AEGIS.server.repositories.database.backend import get_database
from AEGIS.server.repositories.queries.session_catalog import select_by_session_id
from AEGIS.server.repositories.schemas import Base
from AEGIS.server.repositories.schemas.models import (
    ChatMessageRecord,
    SessionCatalogRecord,
)
from sqlalchemy import func, select


class SessionCatalogRepository:
    def __init__(self) -> None:
        backend = get_database().backend
        self._session_factory = backend.session
        Base.metadata.create_all(backend.engine)

    def upsert_for_session(self, *, session_id: int, models: dict[str, Any]) -> None:
        with self._session_factory() as session:
            record = session.execute(select_by_session_id(session_id)).scalars().first()
            message_count = session.scalar(
                select(func.count())
                .select_from(ChatMessageRecord)
                .where(ChatMessageRecord.session_id == session_id)
            )
            if record is None:
                record = SessionCatalogRecord(
                    session_id=session_id,
                    user_id=None,
                    models_json=json.dumps(models),
                    start_time=datetime.utcnow(),
                    duration_seconds=0.0,
                    num_messages=int(message_count or 0),
                )
                session.add(record)
            else:
                record.models_json = json.dumps(models)
                record.num_messages = int(message_count or record.num_messages)
                record.duration_seconds = max(
                    0.0,
                    (datetime.utcnow() - record.start_time).total_seconds(),
                )
            session.commit()
