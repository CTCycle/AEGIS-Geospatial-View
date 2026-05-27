from __future__ import annotations

from dataclasses import asdict
import json
import time

from server.configurations import get_server_settings
from server.repositories.database.initializer import initialize_database
from server.common.logger import logger


###############################################################################
if __name__ == "__main__":
    start = time.perf_counter()
    logger.info("Starting database initialization")    
    initialize_database()
    elapsed = time.perf_counter() - start
    logger.info("Database initialization completed in %.2f seconds", elapsed)
