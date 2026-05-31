from __future__ import annotations

import sqlalchemy

from server.common.logger import logger
from server.configurations import DatabaseSettings, get_server_settings
from server.repositories.database.postgres import PostgresRepository
from server.repositories.database.sqlite import SQLiteRepository
from server.repositories.schemas import Base


def initialize_sqlite_database(settings: DatabaseSettings | None = None) -> None:
    resolved_settings = settings or get_server_settings().database
    repository = SQLiteRepository(resolved_settings)
    Base.metadata.create_all(repository.engine)
    logger.info("Ensured local SQLite schema at %s", repository.db_path)


def validate_postgres_schema(settings: DatabaseSettings | None = None) -> None:
    resolved_settings = settings or get_server_settings().database
    repository = PostgresRepository(resolved_settings)
    existing = set(sqlalchemy.inspect(repository.engine).get_table_names())
    required = set(Base.metadata.tables.keys())
    missing = sorted(required - existing)
    if missing:
        raise ValueError(
            "PostgreSQL schema is missing required tables. "
            f"Missing: {', '.join(missing)}"
        )


def initialize_database(settings: DatabaseSettings | None = None) -> None:
    resolved_settings = settings or get_server_settings().database
    if resolved_settings.embedded_database:
        initialize_sqlite_database(resolved_settings)
        return

    repository = PostgresRepository(resolved_settings)
    Base.metadata.create_all(repository.engine)
    logger.info(
        "Ensured PostgreSQL schema in %s",
        resolved_settings.database_name,
    )
