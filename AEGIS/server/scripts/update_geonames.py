from __future__ import annotations

from AEGIS.server.packages.logger import logger
from AEGIS.server.packages.utils.updater import GeonamesUpdater

###############################################################################
if __name__ == "__main__":
    logger.info("Starting sanitized geonames update process")
    updater = GeonamesUpdater()
    updater.update()
