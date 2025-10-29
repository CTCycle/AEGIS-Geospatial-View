from __future__ import annotations

from AEGIS.app.utils.repository.database import database
from AEGIS.app.utils.updater import GeonamesUpdater

from AEGIS.app.logger import logger


###############################################################################
if __name__ == "__main__":
    logger.info("Starting sanitized geonames update process")
    database.initialize_database()
    updater = GeonamesUpdater()
    updater.update()
