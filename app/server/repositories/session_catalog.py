from __future__ import annotations

import json
from typing import Any

from sqlalchemy import func, select

from server.common.time import utc_now_naive
from server.repositories.database.backend import get_database
from server.repositories.schemas import Base
from server.repositories.schemas.models import (
    ChatMessageRecord,
    SessionCatalogRecord,
)


class SessionCatalogRepository:
    def __init__(self) -> None:
        backend = get_database().backend
        self._session_factory = backend.session
        Base.metadata.create_all(backend.engine)

    def upsert_for_session(self, *, session_id: int, models: dict[str, Any]) -> None:
        with self._session_factory() as session:
            record = (
                session.execute(
                    select(SessionCatalogRecord).where(
                        SessionCatalogRecord.session_id == session_id
                    )
                )
                .scalars()
                .first()
            )
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
                    start_time=utc_now_naive(),
                    duration_seconds=0.0,
                    num_messages=int(message_count or 0),
                )
                session.add(record)
            else:
                record.models_json = json.dumps(models)
                record.num_messages = int(message_count or record.num_messages)
                record.duration_seconds = max(
                    0.0,
                    (utc_now_naive() - record.start_time).total_seconds(),
                )
            session.commit()
