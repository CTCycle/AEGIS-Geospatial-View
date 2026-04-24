from __future__ import annotations

from collections.abc import Callable
from functools import cache
from typing import Any, Protocol

from AEGIS.server.configurations import DatabaseSettings, get_server_settings
from AEGIS.server.repositories.database.initializer import validate_postgres_schema
from AEGIS.server.repositories.database.postgres import PostgresRepository
from AEGIS.server.repositories.database.sqlite import SQLiteRepository
from AEGIS.server.common.logger import logger


###############################################################################
class DatabaseBackend(Protocol):
    db_path: str | None
    engine: Any
    session: Callable[[], Any]

    # -------------------------------------------------------------------------
    def load_from_database(self, table_name: str) -> list[dict[str, Any]]: ...

    # -------------------------------------------------------------------------
    def upsert_into_database(
        self, records: list[dict[str, Any]], table_name: str
    ) -> None: ...

    # -------------------------------------------------------------------------
    def count_rows(self, table_name: str) -> int: ...

    # -------------------------------------------------------------------------
    def list_columns(self, table_name: str) -> list[str]: ...


BackendFactory = Callable[[DatabaseSettings], DatabaseBackend]


# -----------------------------------------------------------------------------
def build_sqlite_backend(settings: DatabaseSettings) -> DatabaseBackend:
    return SQLiteRepository(settings)


# -----------------------------------------------------------------------------
def build_postgres_backend(settings: DatabaseSettings) -> DatabaseBackend:
    return PostgresRepository(settings)


BACKEND_FACTORIES: dict[str, BackendFactory] = {
    "sqlite": build_sqlite_backend,
    "postgres": build_postgres_backend,
}


# [DATABASE]
###############################################################################
class AEGISDatabase:
    def __init__(self) -> None:
        self.settings = get_server_settings().database
        self.backend = self._build_backend(self.settings.embedded_database)

    # -------------------------------------------------------------------------
    def _build_backend(self, is_embedded: bool) -> DatabaseBackend:
        backend_name = "sqlite" if is_embedded else (self.settings.engine or "postgres")
        normalized_name = backend_name.lower()
        logger.info("Initializing %s database backend", backend_name)
        if normalized_name not in BACKEND_FACTORIES:
            raise ValueError(f"Unsupported database engine: {backend_name}")
        factory = BACKEND_FACTORIES[normalized_name]
        backend = factory(self.settings)
        if normalized_name != "sqlite":
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


@cache
def get_database() -> AEGISDatabase:
    return AEGISDatabase()


class _DatabaseProxy:
    def __getattr__(self, name: str) -> Any:
        return getattr(get_database(), name)


database = _DatabaseProxy()
