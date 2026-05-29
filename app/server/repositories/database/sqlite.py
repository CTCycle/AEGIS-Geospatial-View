from __future__ import annotations

import os

import sqlalchemy
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from server.configurations import DatabaseSettings
from server.repositories.database.orm_table_operations import SqlAlchemyTableOperationsMixin
from server.repositories.schemas import Base
from server.common.constants import DATABASE_FILENAME, RESOURCES_PATH


# [SQLITE DATABASE]
###############################################################################
class SQLiteRepository(SqlAlchemyTableOperationsMixin):
    warn_on_missing_table = True

    def __init__(self, settings: DatabaseSettings) -> None:
        self.db_path: str | None = os.path.join(RESOURCES_PATH, DATABASE_FILENAME)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.engine: Engine = sqlalchemy.create_engine(
            f"sqlite:///{self.db_path}", echo=False, future=True
        )
        self.session_factory = sessionmaker(bind=self.engine, future=True)
        self.session = self.session_factory
        self.insert_batch_size = settings.insert_batch_size

    # -------------------------------------------------------------------------
    def ensure_schema(self) -> None:
        Base.metadata.create_all(self.engine)

    # -------------------------------------------------------------------------
    def _insert_statement(self, table_cls: type[object], records: list[dict[str, object]]):
        return sqlite_insert(table_cls).values(records)
