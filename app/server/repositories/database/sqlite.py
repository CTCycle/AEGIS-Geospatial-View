from __future__ import annotations

from pathlib import Path

from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import Engine

from server.configurations import DatabaseSettings, get_server_settings
from server.repositories.database.orm_table_operations import (
    SqlAlchemyTableOperationsMixin,
)
from server.repositories.database.engine import build_engine, build_session_factory
from server.repositories.schemas import Base


# [SQLITE DATABASE]


###############################################################################
class SQLiteRepository(SqlAlchemyTableOperationsMixin):
    warn_on_missing_table = True

    # -------------------------------------------------------------------------
    def __init__(self, settings: DatabaseSettings | None = None) -> None:
        self.settings = settings or get_server_settings().database
        db_path = Path(self.settings.database_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = str(db_path)
        self.engine: Engine = build_engine(self.settings)
        self.session_factory = build_session_factory(self.engine)
        self.session = self.session_factory
        self.insert_batch_size = self.settings.insert_batch_size

    # -------------------------------------------------------------------------
    def ensure_schema(self) -> None:
        Base.metadata.create_all(self.engine)

    # -------------------------------------------------------------------------
    def _insert_statement(
        self, table_cls: type[object], records: list[dict[str, object]]
    ):
        return sqlite_insert(table_cls).values(records)
