from __future__ import annotations

import os

import sqlalchemy
from sqlalchemy.exc import SQLAlchemyError

from server.configurations import DatabaseSettings, get_server_settings
from server.repositories.database.postgres import PostgresRepository
from server.repositories.database.sqlite import SQLiteRepository
from server.repositories.schemas import Base
from server.common.logger import logger


# -----------------------------------------------------------------------------
def initialize_sqlite_database(settings: DatabaseSettings) -> None:
    repository = SQLiteRepository(settings)
    Base.metadata.create_all(repository.engine)
    logger.info("Initialized SQLite database at %s", repository.db_path)


# -----------------------------------------------------------------------------
def should_initialize_sqlite_database(settings: DatabaseSettings) -> bool:
    repository = SQLiteRepository(settings)
    db_path = repository.db_path
    if not db_path:
        return False
    return not os.path.exists(db_path)


# -----------------------------------------------------------------------------
def ensure_postgres_database(settings: DatabaseSettings) -> str:
    if not settings.host:
        raise ValueError("Database host is required for PostgreSQL initialization.")
    if not settings.username:
        raise ValueError("Database username is required for PostgreSQL initialization.")
    if not settings.database_name:
        raise ValueError("Database name is required for PostgreSQL initialization.")

    repository = PostgresRepository(settings)
    Base.metadata.create_all(repository.engine)
    logger.info("Ensured PostgreSQL tables exist in %s", settings.database_name)
    return str(settings.database_name)


def validate_postgres_schema(settings: DatabaseSettings) -> None:
    repository = PostgresRepository(settings)
    existing = set(sqlalchemy.inspect(repository.engine).get_table_names())
    required = set(Base.metadata.tables.keys())
    missing = sorted(required - existing)
    if missing:
        raise ValueError(
            "PostgreSQL schema is missing required tables. "
            f"Run the external initialization script first. Missing: {', '.join(missing)}"
        )


# -----------------------------------------------------------------------------
def run_database_initialization() -> None:
    settings = get_server_settings().database
    if settings.embedded_database:
        repository = SQLiteRepository(settings)
        Base.metadata.create_all(repository.engine)
        if should_initialize_sqlite_database(settings):
            logger.info("Initialized SQLite database at %s", repository.db_path)
        else:
            logger.info("SQLite database already exists; schema ensured.")
        return

    engine_name = (settings.engine or "").lower()
    if engine_name != "postgresql+psycopg":
        raise ValueError(f"Unsupported database engine: {settings.engine}")

    ensure_postgres_database(settings)


# -----------------------------------------------------------------------------
def initialize_database() -> None:
    try:
        run_database_initialization()
    except (SQLAlchemyError, ValueError) as exc:
        logger.error("Database initialization failed: %s", exc)
        raise SystemExit(1) from exc
    except Exception as exc:
        logger.exception("Unexpected error during database initialization.")
        raise SystemExit(1) from exc
