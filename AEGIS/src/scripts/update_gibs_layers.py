from __future__ import annotations

from AEGIS.src.packages.logger import logger
from AEGIS.src.packages.utils.repository.database import database
from AEGIS.src.packages.utils.updater import GIBSLayersUpdater

###############################################################################
if __name__ == "__main__":
    if database.requires_sqlite_initialization():
        logger.info("Database not found, creating instance and making all tables")
        database.initialize_database()

    logger.info("Starting NASA GIBS layer synchronization")
    updater = GIBSLayersUpdater()
    updater.update()
