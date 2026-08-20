from __future__ import annotations

from typing import Any

from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.engine import Engine

from server.configurations import DatabaseSettings
from server.repositories.database.orm_table_operations import (
    SqlAlchemyTableOperationsMixin,
)
from server.repositories.database.engine import build_engine, build_session_factory

###############################################################################
class PostgresRepository(SqlAlchemyTableOperationsMixin):
    warn_on_missing_table = False

    # -------------------------------------------------------------------------
    def __init__(self, settings: DatabaseSettings) -> None:
        if not settings.host:
            raise ValueError("Database host must be provided for external database.")
        if not settings.database_name:
            raise ValueError("Database name must be provided for external database.")
        if not settings.username:
            raise ValueError(
                "Database username must be provided for external database."
            )

        if settings.engine != "postgresql+psycopg":
            raise ValueError(f"Unsupported database engine: {settings.engine}")
        self.db_path: str | None = None
        self.settings = settings
        self.engine: Engine = build_engine(settings)
        self.session_factory = build_session_factory(self.engine)
        self.session = self.session_factory
        self.insert_batch_size = settings.insert_batch_size

    # -------------------------------------------------------------------------
    def _insert_statement(
        self,
        table_cls: type[Any],
        records: list[dict[str, object]],
    ) -> Any:
        return postgres_insert(table_cls).values(records)
