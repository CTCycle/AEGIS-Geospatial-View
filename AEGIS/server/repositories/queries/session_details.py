from __future__ import annotations

from sqlalchemy import select

from AEGIS.server.repositories.schemas.models import SessionDetailsRecord


def select_by_session_id(session_id: int):
    return select(SessionDetailsRecord).where(SessionDetailsRecord.session_id == session_id)
