from __future__ import annotations

import json
from typing import Any

from server.common.time import utc_now_naive
from server.repositories.database.backend import get_database
from server.repositories.schemas import Base
from server.repositories.schemas.models import SessionDetailsRecord


class SessionDetailsRepository:
    def __init__(self) -> None:
        backend = get_database().backend
        self._session_factory = backend.session
        Base.metadata.create_all(backend.engine)

    def insert_turn(
        self,
        *,
        session_id: int,
        message_id: int,
        user_message: str,
        chat_response: str,
        extracted_info: dict[str, Any],
        response_time: float,
        has_triggered_search: bool,
    ) -> None:
        with self._session_factory() as session:
            record = SessionDetailsRecord(
                session_id=session_id,
                message_id=message_id,
                user_message=user_message,
                chat_response=chat_response,
                extracted_info_json=json.dumps(extracted_info),
                timestamp=utc_now_naive(),
                response_time=response_time,
                has_triggered_search=has_triggered_search,
            )
            session.add(record)
            session.commit()
