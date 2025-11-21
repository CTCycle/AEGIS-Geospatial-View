from __future__ import annotations

from AEGIS.src.packages.logger import logger
from AEGIS.src.packages.utils.repository.database import database
from AEGIS.src.packages.utils.updater import GeonamesUpdater

###############################################################################
if __name__ == "__main__":
    logger.info("Starting sanitized geonames update process")
    updater = GeonamesUpdater()
    updater.update()
