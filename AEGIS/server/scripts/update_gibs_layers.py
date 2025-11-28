from __future__ import annotations

from AEGIS.server.packages.logger import logger
from AEGIS.server.packages.utils.updater import GIBSLayersUpdater

###############################################################################
if __name__ == "__main__":
    logger.info("Starting NASA GIBS layer synchronization")
    updater = GIBSLayersUpdater()
    updater.update()
