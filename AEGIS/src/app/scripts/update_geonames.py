from __future__ import annotations

import os

from AEGIS.src.packages.utils.repository.database import database
from AEGIS.src.packages.utils.updater import GeonamesUpdater

from AEGIS.src.packages.logger import logger


###############################################################################
if __name__ == "__main__":
    if database.db_path and not os.path.exists(database.db_path):
        logger.info("Database not found, creating instance and making all tables")
        database.initialize_database()
        
    logger.info("Starting sanitized geonames update process")   
    updater = GeonamesUpdater()
    updater.update()
