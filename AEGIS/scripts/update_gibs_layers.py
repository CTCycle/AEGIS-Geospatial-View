from __future__ import annotations

from AEGIS.server.utils.logger import logger
from AEGIS.server.services.updater.gibs import GIBSLayersUpdater

###############################################################################
if __name__ == "__main__":
    logger.info("Starting NASA GIBS layer synchronization")
    updater = GIBSLayersUpdater()
    updater.update()
