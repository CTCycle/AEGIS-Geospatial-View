from __future__ import annotations

import os

import sqlalchemy
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from server.configurations import DatabaseSettings, get_server_settings
from server.repositories.database.orm_table_operations import SqlAlchemyTableOperationsMixin
from server.repositories.schemas import Base


# [SQLITE DATABASE]
###############################################################################
class SQLiteRepository(SqlAlchemyTableOperationsMixin):
    warn_on_missing_table = True

    def __init__(self, settings: DatabaseSettings | None = None) -> None:
        self.settings = settings or get_server_settings().database
        self.db_path = self.settings.database_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.engine: Engine = sqlalchemy.create_engine(
            f"sqlite:///{self.db_path}", echo=False, future=True
        )
        self.session_factory = sessionmaker(bind=self.engine, future=True)
        self.session = self.session_factory
        self.insert_batch_size = self.settings.insert_batch_size

    # -------------------------------------------------------------------------
    def ensure_schema(self) -> None:
        Base.metadata.create_all(self.engine)

    # -------------------------------------------------------------------------
    def _insert_statement(self, table_cls: type[object], records: list[dict[str, object]]):
        return sqlite_insert(table_cls).values(records)
