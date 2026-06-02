from __future__ import annotations

from functools import cache
from typing import Any, Protocol

from server.configurations import get_server_settings
from server.repositories.database.initializer import validate_postgres_schema
from server.repositories.schemas import Base
from server.repositories.database.postgres import PostgresRepository
from server.repositories.database.sqlite import SQLiteRepository


###############################################################################
class DatabaseBackend(Protocol):
    db_path: str | None
    engine: Any
    session: Any

    # -------------------------------------------------------------------------
    def load_from_database(self, table_name: str) -> list[dict[str, Any]]: ...

    # -------------------------------------------------------------------------
    def upsert_into_database(
        self, records: list[dict[str, Any]], table_name: str
    ) -> None: ...

    # -------------------------------------------------------------------------
    def count_rows(self, table_name: str) -> int: ...

    # -------------------------------------------------------------------------
    def count_records(self, model: type[Base]) -> int: ...

    # -------------------------------------------------------------------------
    def list_columns(self, table_name: str) -> list[str]: ...

class AEGISDatabase:
    def __init__(self) -> None:
        self.settings = get_server_settings().database
        self.backend = self._build_backend()

    def _build_backend(self) -> DatabaseBackend:
        if self.settings.embedded_database:
            return SQLiteRepository(self.settings)

        backend = PostgresRepository(self.settings)
        validate_postgres_schema(self.settings)
        return backend

    # -------------------------------------------------------------------------
    @property
    def db_path(self) -> str | None:
        return getattr(self.backend, "db_path", None)

    # -------------------------------------------------------------------------
    def load_from_database(self, table_name: str) -> list[dict[str, Any]]:
        return self.backend.load_from_database(table_name)

    # -------------------------------------------------------------------------
    def upsert_into_database(
        self, records: list[dict[str, Any]], table_name: str
    ) -> None:
        self.backend.upsert_into_database(records, table_name)

    # -------------------------------------------------------------------------
    def count_rows(self, table_name: str) -> int:
        return self.backend.count_rows(table_name)

    # -------------------------------------------------------------------------
    def list_columns(self, table_name: str) -> list[str]:
        return self.backend.list_columns(table_name)

    # -------------------------------------------------------------------------
    def count_records(self, model: type[Base]) -> int:
        return self.backend.count_records(model)


@cache
def get_database() -> AEGISDatabase:
    return AEGISDatabase()


