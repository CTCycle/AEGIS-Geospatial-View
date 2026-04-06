from __future__ import annotations

from sqlalchemy import select

from AEGIS.server.repositories.schemas.models import SessionCatalogRecord


def select_by_session_id(session_id: int):
    return select(SessionCatalogRecord).where(SessionCatalogRecord.session_id == session_id)
