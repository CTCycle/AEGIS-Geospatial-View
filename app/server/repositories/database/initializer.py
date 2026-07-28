from __future__ import annotations

import sqlalchemy

from server.common.logger import logger
from server.repositories.catalog.reference_seeder import (
    ReferenceCatalogSeeder,
    ReferenceSeedResult,
)
from server.repositories.database.contracts import DatabaseBackend
from server.repositories.schemas import Base
from server.services.catalog.loader import load_reference_catalog

###############################################################################
def initialize_database(database: DatabaseBackend) -> None:
    Base.metadata.create_all(database.engine)
    logger.info("Ensured relational schema using active database backend.")

###############################################################################
def validate_postgres_schema(database: DatabaseBackend) -> None:
    existing = set(sqlalchemy.inspect(database.engine).get_table_names())
    required = set(Base.metadata.tables.keys())
    missing = sorted(required - existing)
    if missing:
        raise ValueError(
            "PostgreSQL schema is missing required tables. "
            f"Missing: {', '.join(missing)}"
        )

###############################################################################
def seed_reference_catalog(database: DatabaseBackend) -> ReferenceSeedResult:
    catalog = load_reference_catalog()
    return ReferenceCatalogSeeder(database).seed_if_needed(catalog)
