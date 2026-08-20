from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection

from server.common.logger import logger
from server.repositories.credential_material import seed_credential_encryption_material
from server.repositories.database.contracts import DatabaseBackend
from server.repositories.database.migration_runner import (
    MigrationResult,
    acquire_postgres_lock,
    migration_lock_timeout,
    release_postgres_lock,
    synchronize_database,
)

###############################################################################
def initialize_database(
    database: DatabaseBackend,
    *,
    on_ready: Callable[[], None] | None = None,
) -> MigrationResult:
    if database.db_path is None:
        _ensure_postgres_database_exists(database)

    def seed_required_data() -> None:
        seed_credential_encryption_material(database)
        if on_ready is not None:
            on_ready()

    result = synchronize_database(database, on_ready=seed_required_data)
    logger.info(
        "Database is ready: fresh=%s, adopted_legacy=%s, migrations_applied=%s",
        result.fresh_database,
        result.adopted_legacy_schema,
        result.migrations_applied,
    )
    return result

###############################################################################
def _ensure_postgres_database_exists(database: DatabaseBackend) -> None:
    target_url = database.engine.url
    target_name = target_url.database
    if not target_name:
        raise ValueError("PostgreSQL database name is required for initialization.")

    maintenance_engine = create_engine(
        target_url.set(database="postgres"),
        future=True,
        isolation_level="AUTOCOMMIT",
        pool_pre_ping=True,
    )
    try:
        with maintenance_engine.connect() as connection:
            acquire_postgres_lock(connection, migration_lock_timeout(database))
            try:
                _ensure_postgres_database_exists_locked(connection, target_name)
            finally:
                release_postgres_lock(connection)
    finally:
        maintenance_engine.dispose()


def _ensure_postgres_database_exists_locked(
    connection: Connection,
    target_name: str,
) -> None:
    exists = connection.scalar(
        text("SELECT 1 FROM pg_database WHERE datname = :database_name"),
        {"database_name": target_name},
    )
    if exists is not None:
        return

    quoted_name = '"' + target_name.replace('"', '""') + '"'
    connection.exec_driver_sql(f"CREATE DATABASE {quoted_name}")
    logger.info("Created PostgreSQL database: %s", target_name)

###############################################################################
