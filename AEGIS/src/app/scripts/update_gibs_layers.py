from __future__ import annotations

from AEGIS.src.packages.logger import logger
from AEGIS.src.packages.utils.repository.database import database
from AEGIS.src.packages.utils.updater import GIBSLayersUpdater


###############################################################################
if __name__ == "__main__":
    logger.info("Starting NASA GIBS layer synchronization")
    database.initialize_database()
    updater = GIBSLayersUpdater()
    updater.update()
