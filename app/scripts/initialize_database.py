from __future__ import annotations

import time

from server.common.logger import logger
from server.configurations import build_database_settings, ensure_environment_loaded
from server.repositories.database.initializer import initialize_database
from server.repositories.database.sqlite import SQLiteRepository
from server.services.catalog.startup import seed_reference_catalog


###############################################################################
if __name__ == "__main__":
    start = time.perf_counter()
    logger.info("Starting database initialization")
    ensure_environment_loaded()
    database = SQLiteRepository(build_database_settings())
    try:
        initialize_database(
            database,
            on_ready=lambda: seed_reference_catalog(database),
        )
        elapsed = time.perf_counter() - start
        logger.info("Database initialization completed in %.2f seconds", elapsed)
    finally:
        database.engine.dispose()
