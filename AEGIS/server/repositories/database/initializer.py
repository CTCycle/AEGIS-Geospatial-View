from __future__ import annotations

import os
import urllib.parse

import sqlalchemy
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.sql.elements import TextClause

from AEGIS.server.configurations import DatabaseSettings, server_settings
from AEGIS.server.repositories.database.postgres import PostgresRepository
from AEGIS.server.repositories.database.sqlite import SQLiteRepository
from AEGIS.server.repositories.schemas import Base
from AEGIS.server.repositories.database.utils import normalize_postgres_engine
from AEGIS.server.utils.logger import logger


###############################################################################
def build_postgres_connect_args(settings: DatabaseSettings) -> dict[str, str | int]:
    connect_args: dict[str, str | int] = {
        "connect_timeout": settings.connect_timeout,
        "client_encoding": "utf8",
    }
    if settings.ssl:
        connect_args["sslmode"] = "require"
        if settings.ssl_ca:
            connect_args["sslrootcert"] = settings.ssl_ca
    return connect_args


# -----------------------------------------------------------------------------
def build_postgres_url(settings: DatabaseSettings, database_name: str) -> str:
    port = settings.port or 5432
    engine_name = normalize_postgres_engine(settings.engine)
    safe_username = urllib.parse.quote_plus(settings.username or "")
    safe_password = urllib.parse.quote_plus(settings.password or "")
    return (
        f"{engine_name}://{safe_username}:{safe_password}"
        f"@{settings.host}:{port}/{database_name}"
    )


# -----------------------------------------------------------------------------
def clone_settings_with_database(
    settings: DatabaseSettings, database_name: str
) -> DatabaseSettings:
    return DatabaseSettings(
        embedded_database=False,
        engine=settings.engine,
        host=settings.host,
        port=settings.port,
        database_name=database_name,
        username=settings.username,
        password=settings.password,
        ssl=settings.ssl,
        ssl_ca=settings.ssl_ca,
        connect_timeout=settings.connect_timeout,
        insert_batch_size=settings.insert_batch_size,
    )


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
def build_postgres_database_exists_statement() -> TextClause:
    return sqlalchemy.text("SELECT 1 FROM pg_database WHERE datname=:name")


# -----------------------------------------------------------------------------
def build_postgres_create_database_statement(database_name: str) -> TextClause:
    safe_database = database_name.replace('"', '""')
    return sqlalchemy.text(
        f'CREATE DATABASE "{safe_database}" WITH ENCODING \'UTF8\' TEMPLATE template0'
    )


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
    settings = server_settings.database
    if settings.embedded_database:
        if not should_initialize_sqlite_database(settings):
            logger.info("SQLite database already exists, skipping initialization.")
            return
        initialize_sqlite_database(settings)
        return

    engine_name = normalize_postgres_engine(settings.engine).lower()
    if engine_name not in {
        "postgres",
        "postgresql",
        "postgresql+psycopg",
        "postgresql+psycopg2",
    }:
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
