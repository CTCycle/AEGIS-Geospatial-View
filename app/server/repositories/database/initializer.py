from __future__ import annotations

import sqlalchemy

from server.common.logger import logger
from server.configurations import DatabaseSettings, get_server_settings
from server.repositories.catalog.reference_seeder import (
    ReferenceCatalogSeeder,
    ReferenceSeedResult,
)
from server.repositories.database.contracts import DatabaseBackend
from server.repositories.database.postgres import PostgresRepository
from server.repositories.database.sqlite import SQLiteRepository
from server.repositories.schemas import Base
from server.services.catalog.loader import load_reference_catalog


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


def initialize_database(
    database: DatabaseBackend | DatabaseSettings | None = None,
) -> None:
    if database is None or isinstance(database, DatabaseSettings):
        resolved_settings = database or get_server_settings().database
        if resolved_settings.embedded_database:
            initialize_sqlite_database(resolved_settings)
            return
        repository = PostgresRepository(resolved_settings)
        Base.metadata.create_all(repository.engine)
        logger.info(
            "Ensured PostgreSQL schema in %s",
            resolved_settings.database_name,
        )
        return

    Base.metadata.create_all(database.engine)
    logger.info("Ensured relational schema using active database backend.")


def seed_reference_catalog(database: DatabaseBackend) -> ReferenceSeedResult:
    catalog = load_reference_catalog()
    return ReferenceCatalogSeeder(database).seed_if_needed(catalog)
