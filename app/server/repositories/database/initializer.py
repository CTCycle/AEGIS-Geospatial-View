from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, text

from server.common.logger import logger
from server.repositories.catalog.reference_seeder import (
    ReferenceCatalogSeeder,
    ReferenceSeedResult,
)
from server.repositories.credential_material import seed_credential_encryption_material
from server.repositories.database.contracts import DatabaseBackend
from server.repositories.schemas import Base
from server.services.catalog.loader import load_reference_catalog

###############################################################################
def initialize_database(database: DatabaseBackend) -> None:
    if database.db_path is not None:
        if Path(database.db_path).exists():
            logger.info("Skipped initialization for existing SQLite database: %s", database.db_path)
            return
    else:
        _ensure_postgres_database_exists(database)

    Base.metadata.create_all(database.engine)
    logger.info("Ensured relational schema using active database backend.")
    seed_credential_encryption_material(database)
    seed_reference_catalog(database)

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
            exists = connection.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :database_name"),
                {"database_name": target_name},
            )
            if exists is not None:
                return

            quoted_name = '"' + target_name.replace('"', '""') + '"'
            connection.exec_driver_sql(f"CREATE DATABASE {quoted_name}")
            logger.info("Created PostgreSQL database: %s", target_name)
    finally:
        maintenance_engine.dispose()

###############################################################################
def seed_reference_catalog(database: DatabaseBackend) -> ReferenceSeedResult:
    catalog = load_reference_catalog()
    return ReferenceCatalogSeeder(database).seed_if_needed(catalog)
