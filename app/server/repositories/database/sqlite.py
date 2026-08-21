from __future__ import annotations

from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.engine import Engine

from server.configurations import DatabaseSettings, get_server_settings
from server.repositories.database.engine import build_engine, build_session_factory
from server.repositories.schemas import Base


# [SQLITE DATABASE]

###############################################################################
class SQLiteRepository:

    # -------------------------------------------------------------------------
    def __init__(self, settings: DatabaseSettings | None = None) -> None:
        self.settings = settings or get_server_settings().database
        db_path = Path(self.settings.database_path)
        self.db_path = str(db_path)
        self.engine: Engine = build_engine(self.settings)
        self.session_factory = build_session_factory(self.engine)
        self.session = self.session_factory

    # -------------------------------------------------------------------------
    def count_records(self, model: type[Base]) -> int:
        with self.session_factory() as session:
            value = session.scalar(select(func.count()).select_from(model)) or 0
        return int(value)
