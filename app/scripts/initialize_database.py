from __future__ import annotations

import time

from server.configurations import get_server_settings
from server.repositories.database import build_database_backend
from server.repositories.database.initializer import initialize_database
from server.common.logger import logger


###############################################################################
if __name__ == "__main__":
    start = time.perf_counter()
    logger.info("Starting database initialization")
    settings = get_server_settings()
    database = build_database_backend(settings.database)
    initialize_database(database)
    elapsed = time.perf_counter() - start
    logger.info("Database initialization completed in %.2f seconds", elapsed)
